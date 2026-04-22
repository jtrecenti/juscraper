"""HTML parsers for eSAJ cjsg results.

Absorbs the 6 near-identical ``cjsg_parse.py`` modules from the courts.
The TJSP version is the canonical reference for ``cjsg_n_pags`` (see
CLAUDE.md) because its cascade of selectors/regex tolerates both the
legacy ``bgcolor=#EEEEEE`` layout and the newer ``td Resultados…``
wording. The parser treats latin-1 as the expected server encoding
(falls back to utf-8 for test samples that were re-saved).
"""
from __future__ import annotations

import glob
import logging
import os
import re

import pandas as pd
import unidecode
from bs4 import BeautifulSoup
from tqdm import tqdm

logger = logging.getLogger("juscraper._esaj.parse")

_ZERO_RESULT_MARKERS = (
    "nenhum resultado",
    "não foram encontrados",
    "sem resultados",
)

_TYPO_FIXES = {
    # latin-1 → utf-8 mangling occasionally seen on the TJSP cjsg page.
    "data_publicassapso": "data_publicacao",
    "argapso_julgador": "orgao_julgador",
}


def cjsg_n_pags(html_source: str) -> int:
    """Extract the total number of pages from a cjsg first-page HTML.

    Uses a cascade of selectors and regex to survive layout changes. See the
    "Extração de número de páginas/resultados em raspadores HTML" section of
    CLAUDE.md for the rationale. Canonical implementation — used by all six
    eSAJ courts.

    Raises:
        ValueError: If the HTML contains a captcha/error marker, if it still
            looks like the search form (POST did not submit), or if no
            pagination marker can be found.

    Returns:
        Number of pages (0 when the search returned no hits, >=1 otherwise).
    """
    soup = BeautifulSoup(html_source, "html.parser")

    # eSAJ returns an HTTP 200 page with error divs when the captcha expires
    # or validation fails. Surface a specific error instead of letting the
    # cascade below raise a confusing "seletor não encontrado".
    error_divs = soup.find_all(
        ["div", "span", "p"], class_=re.compile(r"error|erro|mensagem.*erro", re.I)
    )
    if error_divs:
        error_text = " ".join(elem.get_text().lower() for elem in error_divs[:3])
        if "captcha" in error_text or "verificação" in error_text:
            raise ValueError(
                "Captcha não foi resolvido. A página pode requerer verificação manual."
            )
        error_msg = " ".join(elem.get_text() for elem in error_divs[:3]).strip()
        if error_msg:
            raise ValueError(f"Erro detectado na página: {error_msg[:200]}")

    page_text = soup.get_text().lower()
    if any(marker in page_text for marker in _ZERO_RESULT_MARKERS):
        return 0

    td_npags = None
    for td in soup.find_all("td"):
        td_text = td.get_text()
        if "Resultados" in td_text or "resultados" in td_text.lower():
            if len(td_text.strip()) < 400:  # guard against matching result rows
                td_npags = td
                break

    if td_npags is None:
        td_npags = soup.find("td", bgcolor="#EEEEEE")

    if td_npags is None:
        td_npags = soup.find("td", class_=re.compile(r".*pag.*", re.I))

    if td_npags is None:
        for td in soup.find_all("td"):
            td_text = td.get_text().lower()
            if "página" in td_text and ("de" in td_text or "total" in td_text):
                td_npags = td
                break

    if td_npags is None:
        results_table = soup.find("table", class_=re.compile(r"fundocinza|resultado", re.I))
        if results_table is None:
            if soup.find("form", id=re.compile(r"form|consulta", re.I)):
                raise ValueError(
                    "Ainda na página de consulta. "
                    "O formulário pode não ter sido submetido corretamente."
                )
            raise ValueError(
                "Não foi possível encontrar o seletor de número de páginas "
                "na resposta HTML. Verifique se a busca retornou resultados "
                "ou se a estrutura da página mudou."
            )
        return 1

    txt_pag = td_npags.get_text()

    encontrados = re.findall(r"\d+$", txt_pag.strip())
    if not encontrados:
        encontrados = re.findall(r"(?<=de )\d+", txt_pag)
    if not encontrados:
        encontrados = re.findall(r"\d+(?=\s*(?:resultado|registro|página))", txt_pag, flags=re.I)
    if not encontrados:
        all_nums = re.findall(r"\d+", txt_pag)
        if all_nums:
            encontrados = [max(all_nums, key=int)]

    if not encontrados:
        raise ValueError(
            "Não foi possível extrair o número de resultados da paginação. "
            f"Formato inesperado encontrado. Texto: {txt_pag[:100]}"
        )

    n_results = int(encontrados[0])
    return (n_results + 19) // 20  # 20 hits per page, ceil div


def _normalize_key(label: str) -> str:
    key = label.replace(":", "").strip().lower()
    key = unidecode.unidecode(key)
    key = key.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
    key = key.replace("_de_", "_").replace("_do_", "_")
    key = re.sub(r"_+", "_", key).strip("_")
    return _TYPO_FIXES.get(key, key)


def _clean_value(value: str) -> str:
    return (
        value
        .replace("\xad", "")       # soft hyphen
        .replace("\u200b", "")    # zero-width space
        .replace("\u200c", "")    # zero-width non-joiner
        .replace("\u200d", "")    # zero-width joiner
    )


def _parse_single_page(path: str) -> pd.DataFrame:
    with open(path, "rb") as fp:
        raw = fp.read()

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = raw.decode("latin1")
        except UnicodeDecodeError:
            content = raw.decode("utf-8", errors="replace")

    soup = BeautifulSoup(content, "html.parser")
    processos: list[dict] = []

    for tr in soup.find_all("tr", class_="fundocinza1"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        details_table = tds[1].find("table")
        if not details_table:
            continue

        dados: dict = {"ementa": ""}

        proc_a = details_table.find("a", class_="esajLinkLogin downloadEmenta")
        if proc_a:
            dados["processo"] = proc_a.get_text(strip=True)
            dados["cd_acordao"] = proc_a.get("cdacordao")
            dados["cd_foro"] = proc_a.get("cdforo")

        for tr_detail in details_table.find_all("tr", class_="ementaClass2"):
            strong = tr_detail.find("strong")
            if not strong:
                continue
            label = strong.get_text(strip=True)

            if "ementa:" in label.lower():
                visible_div = None
                for div in tr_detail.find_all("div", align="justify"):
                    style = str(div.get("style", "display: none;"))
                    if "display: none" not in style:
                        visible_div = div
                        break
                if visible_div:
                    ementa_text = visible_div.get_text(" ", strip=True)
                else:
                    ementa_text = tr_detail.get_text(" ", strip=True)
                dados["ementa"] = ementa_text.replace("Ementa:", "").strip()
                continue

            full_text = tr_detail.get_text(" ", strip=True)
            value = _clean_value(full_text.replace(label, "", 1).strip().lstrip(":").strip())

            key = _normalize_key(label)
            if key == "outros_numeros":
                continue
            if "data_publicacao" in key:
                key = "data_publicacao"
                for stamp in ("Data de publicação:", "Data de Publicação:", "Data de publicassapso:"):
                    value = value.replace(stamp, "")
                value = value.strip()
            elif "orgao_julgador" in key:
                key = "orgao_julgador"
                for stamp in ("Órgão julgador:", "Orgão julgador:", "argapso julgador:"):
                    value = value.replace(stamp, "")
                value = value.strip()

            dados[key] = value

        processos.append(dados)

    df = pd.DataFrame(processos)
    if "ementa" in df.columns:
        cols = [c for c in df.columns if c != "ementa"] + ["ementa"]
        df = df[cols]
    return df


def cjsg_parse_manager(path: str) -> pd.DataFrame:
    """Parse downloaded cjsg HTML files into a single DataFrame.

    Args:
        path: File or directory containing downloaded HTML files.

    Returns:
        Combined DataFrame. Empty when no files parse successfully.
    """
    if os.path.isfile(path):
        return _parse_single_page(path)

    arquivos = glob.glob(os.path.join(path, "**", "*.ht*"), recursive=True)
    arquivos = [f for f in arquivos if os.path.isfile(f)]

    result: list[pd.DataFrame] = []
    for file in tqdm(arquivos, desc="Processando documentos"):
        try:
            single = _parse_single_page(file)
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as exc:
            logger.error("Erro ao processar %s: %s", file, exc)
            continue
        if single is not None and not single.empty:
            result.append(single)

    if not result:
        return pd.DataFrame()
    return pd.concat(result, ignore_index=True)
