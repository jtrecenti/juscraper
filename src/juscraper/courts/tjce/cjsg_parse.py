"""
Parse of cases from the TJCE Consulta de Julgados de Segundo Grau (CJSG).
TJCE uses the same eSAJ platform as TJSP, so the HTML structure is identical.
"""
import os
import glob
import re
import logging

import pandas as pd
import unidecode
from bs4 import BeautifulSoup
from tqdm import tqdm

logger = logging.getLogger("juscraper.tjce.cjsg_parse")


def cjsg_n_pags(html_source: str) -> int:
    """Extract total number of pages from the CJSG results HTML.

    The pagination element contains text like ``Resultados 1 a 20 de 397119``.
    We extract the last number and divide by 20 (results per page).
    """
    soup = BeautifulSoup(html_source, "html.parser")

    page_text = soup.get_text().lower()
    if "nenhum resultado" in page_text or "não foram encontrados" in page_text:
        return 0

    # Look for td containing "Resultados" (eSAJ standard)
    td_npags = None
    for td in soup.find_all("td"):
        td_text = td.get_text()
        if "Resultados" in td_text and len(td_text.strip()) < 200:
            td_npags = td
            break

    if td_npags is None:
        td_npags = soup.find("td", bgcolor="#EEEEEE")

    if td_npags is None:
        results_table = soup.find("table", class_=re.compile(r"fundocinza|resultado", re.I))
        if results_table is None:
            if soup.find("form", id=re.compile(r"form|consulta", re.I)):
                raise ValueError(
                    "Ainda na página de consulta. O formulário pode não ter sido submetido."
                )
            raise ValueError("Não foi possível encontrar o seletor de número de páginas.")
        return 1

    txt_pag = td_npags.get_text()
    encontrados = re.findall(r"\d+$", txt_pag.strip())
    if not encontrados:
        encontrados = re.findall(r"(?<=de )\d+", txt_pag)
    if not encontrados:
        all_nums = re.findall(r"\d+", txt_pag)
        if all_nums:
            encontrados = [max(all_nums, key=int)]
    if not encontrados:
        raise ValueError(f"Não foi possível extrair número de resultados. Texto: {txt_pag[:100]}")

    n_results = int(encontrados[0])
    return (n_results + 19) // 20


def _parse_single_page(path: str) -> pd.DataFrame:
    """Parse a single CJSG HTML result page into a DataFrame."""
    with open(path, "rb") as f:
        raw = f.read()

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = raw.decode("latin1")
        except UnicodeDecodeError:
            content = raw.decode("utf-8", errors="replace")

    soup = BeautifulSoup(content, "html.parser")
    processos = []

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
                    ementa_text = ementa_text.replace("Ementa:", "").strip()
                    dados["ementa"] = ementa_text
                else:
                    full_text = tr_detail.get_text(" ", strip=True)
                    dados["ementa"] = full_text.replace("Ementa:", "").strip()
            else:
                full_text = tr_detail.get_text(" ", strip=True)
                value = full_text.replace(label, "", 1).strip().lstrip(":").strip()
                value = value.replace("\xad", "").replace("\u200b", "")

                key = label.replace(":", "").strip().lower()
                key = unidecode.unidecode(key)
                key = key.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                key = key.replace("_de_", "_").replace("_do_", "_")
                key = re.sub(r"_+", "_", key).strip("_")

                if key != "outros_numeros":
                    if "data_publicacao" in key:
                        key = "data_publicacao"
                    elif "orgao_julgador" in key:
                        key = "orgao_julgador"
                    dados[key] = value

        processos.append(dados)

    df = pd.DataFrame(processos)
    if "ementa" in df.columns:
        cols = [c for c in df.columns if c != "ementa"] + ["ementa"]
        df = df[cols]
    return df


def cjsg_parse_manager(path: str) -> pd.DataFrame:
    """Parse downloaded CJSG HTML files into a DataFrame.

    Parameters
    ----------
    path : str or Path
        File or directory containing downloaded HTML files.

    Returns
    -------
    pd.DataFrame
        Combined results from all pages.
    """
    if os.path.isfile(path):
        return _parse_single_page(path)

    result = []
    arquivos = glob.glob(os.path.join(path, "**", "*.ht*"), recursive=True)
    arquivos = [f for f in arquivos if os.path.isfile(f)]
    for file in tqdm(arquivos, desc="Processando CJSG TJCE"):
        try:
            single = _parse_single_page(file)
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
            logger.error("Erro ao processar %s: %s", file, e)
            continue
        if single is not None:
            result.append(single)

    if not result:
        return pd.DataFrame()
    return pd.concat(result, ignore_index=True)
