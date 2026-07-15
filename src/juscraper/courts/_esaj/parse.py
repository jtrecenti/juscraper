"""HTML parsers for eSAJ cjsg results.

Absorbs the 6 near-identical ``cjsg_parse.py`` modules from the courts.
The TJSP version is the canonical reference for ``cjsg_n_pags`` (see
CLAUDE.md) because its cascade of selectors/regex tolerates both the
legacy ``bgcolor=#EEEEEE`` layout and the newer ``td Resultados…``
wording. The parser treats latin-1 as the expected server encoding
(falls back to utf-8 for test samples that were re-saved).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import cast

import pandas as pd
import unidecode
from bs4 import BeautifulSoup
from bs4.element import Tag
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

_ERROR_CLASS_RE = re.compile(r"error|erro|mensagem.*erro", re.I)
_FORM_ID_RE = re.compile(r"form|consulta", re.I)
_PAGINATION_CLASS_RE = re.compile(r".*pag.*", re.I)
_RESULT_TABLE_CLASS_RE = re.compile(r"fundocinza|resultado", re.I)
_PAGINATION_COUNT_PATTERNS = (
    re.compile(r"\d+$"),
    re.compile(r"(?<=de )\d+"),
    re.compile(r"\d+(?=\s*(?:resultado|registro|página))", re.I),
)
_FIELD_STAMPS = {
    "data_publicacao": (
        "Data de publicação:",
        "Data de Publicação:",
        "Data de publicassapso:",
    ),
    "orgao_julgador": (
        "Órgão julgador:",
        "Orgão julgador:",
        "argapso julgador:",
    ),
}


def _raise_page_error(soup: BeautifulSoup) -> None:
    error_divs = soup.find_all(["div", "span", "p"], class_=_ERROR_CLASS_RE)
    if not error_divs:
        return

    error_text = " ".join(elem.get_text().lower() for elem in error_divs[:3])
    if "captcha" in error_text or "verificação" in error_text:
        raise ValueError(
            "Captcha não foi resolvido. A página pode requerer verificação manual."
        )

    error_msg = " ".join(elem.get_text() for elem in error_divs[:3]).strip()
    if error_msg:
        raise ValueError(f"Erro detectado na página: {error_msg[:200]}")


def _has_zero_results(soup: BeautifulSoup) -> bool:
    page_text = soup.get_text().lower()
    return any(marker in page_text for marker in _ZERO_RESULT_MARKERS)


def _find_short_results_cell(soup: BeautifulSoup) -> Tag | None:
    for cell in soup.find_all("td"):
        text = cell.get_text()
        if "resultados" in text.lower() and len(text.strip()) < 400:
            return cell
    return None


def _find_page_summary_cell(soup: BeautifulSoup) -> Tag | None:
    for cell in soup.find_all("td"):
        text = cell.get_text().lower()
        if "página" in text and ("de" in text or "total" in text):
            return cell
    return None


def _find_pagination_element(soup: BeautifulSoup) -> Tag | None:
    return (
        _find_short_results_cell(soup)
        or soup.find("td", bgcolor="#EEEEEE")
        or soup.find("td", class_=_PAGINATION_CLASS_RE)
        or _find_page_summary_cell(soup)
    )


def _count_result_rows_or_raise(soup: BeautifulSoup) -> int:
    results_table = soup.find("table", class_=_RESULT_TABLE_CLASS_RE)
    if results_table is not None:
        n_rows = len(soup.find_all("tr", class_="fundocinza1"))
        return max(n_rows, 1)

    if soup.find("form", id=_FORM_ID_RE):
        raise ValueError(
            "Ainda na página de consulta. "
            "O formulário pode não ter sido submetido corretamente."
        )
    raise ValueError(
        "Não foi possível encontrar o seletor de número de páginas "
        "na resposta HTML. Verifique se a busca retornou resultados "
        "ou se a estrutura da página mudou."
    )


def _extract_pagination_count(text: str) -> int | None:
    stripped_text = text.strip()
    for pattern in _PAGINATION_COUNT_PATTERNS:
        match = pattern.search(stripped_text)
        if match is not None:
            return int(match.group())

    all_numbers = re.findall(r"\d+", text)
    if all_numbers:
        return max(int(number) for number in all_numbers)
    return None


def cjsg_n_results(html_source: str) -> int:
    """Extract the total number of results from a cjsg first-page HTML.

    Canonical implementation — used by all six eSAJ courts. Sibling of
    :func:`cjsg_n_pags`, which is now a thin wrapper that divides by the
    20-hits-per-page constant.

    Used by the ``count_only=True`` short-circuit in
    :meth:`EsajSearchScraper.cjsg` (issue #92) and by
    :func:`juscraper.courts._esaj.download.download_cjsg_pages` to size the
    pagination loop.

    Uses a cascade of selectors and regex to survive layout changes. See the
    "Extração de número de páginas/resultados em raspadores HTML" section of
    CLAUDE.md for the rationale.

    Fallback for the "results table present but pagination marker missing"
    edge case: counts ``tr.fundocinza1`` rows on the page (the row class used
    by the eSAJ results table). Ensures ``count_only`` returns a meaningful
    estimate instead of a hardcoded ``1``.

    Raises:
        ValueError: If the HTML contains a captcha/error marker, if it still
            looks like the search form (POST did not submit), or if no
            pagination marker can be found.

    Returns:
        Number of results (0 when the search returned no hits, >=1 otherwise).
    """
    soup = BeautifulSoup(html_source, "html.parser")

    _raise_page_error(soup)
    if _has_zero_results(soup):
        return 0

    pagination_element = _find_pagination_element(soup)
    if pagination_element is None:
        return _count_result_rows_or_raise(soup)

    pagination_text = pagination_element.get_text()
    count = _extract_pagination_count(pagination_text)
    if count is None:
        raise ValueError(
            "Não foi possível extrair o número de resultados da paginação. "
            f"Formato inesperado encontrado. Texto: {pagination_text[:100]}"
        )
    return count


def cjsg_n_pags(html_source: str) -> int:
    """Extract the total number of pages from a cjsg first-page HTML.

    Thin wrapper over :func:`cjsg_n_results` that converts result count into
    page count via ``ceil(n_results / 20)`` (eSAJ serves 20 hits per page).

    Raises:
        ValueError: Same conditions as :func:`cjsg_n_results`.

    Returns:
        Number of pages (0 when the search returned no hits, >=1 otherwise).
    """
    n_results = cjsg_n_results(html_source)
    if n_results == 0:
        return 0
    return (n_results + 19) // 20


def _normalize_key(label: str) -> str:
    key = label.replace(":", "").strip().lower()
    key = unidecode.unidecode(key)
    key = key.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
    key = key.replace("_de_", "_").replace("_do_", "_")
    key = re.sub(r"_+", "_", key).strip("_")
    return _TYPO_FIXES.get(key, key)


def _clean_value(value: str) -> str:
    return (
        value.replace("\xad", "")  # soft hyphen
        .replace("\u200b", "")  # zero-width space
        .replace("\u200c", "")  # zero-width non-joiner
        .replace("\u200d", "")  # zero-width joiner
    )


def _read_html(path: str) -> str:
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin1")


def _extract_process_metadata(details_table: Tag, data: dict) -> None:
    process_link = details_table.find("a", class_="esajLinkLogin downloadEmenta")
    if process_link is None:
        return

    data["processo"] = process_link.get_text(strip=True)
    data["cd_acordao"] = process_link.get("cdacordao")
    data["cd_foro"] = process_link.get("cdforo")


def _extract_ementa(detail_row: Tag) -> str:
    for div in detail_row.find_all("div", align="justify"):
        style = str(div.get("style", "display: none;"))
        if "display: none" not in style:
            text = cast(str, div.get_text(" ", strip=True))
            return text.replace("Ementa:", "").strip()
    text = cast(str, detail_row.get_text(" ", strip=True))
    return text.replace("Ementa:", "").strip()


def _canonicalize_field(key: str, value: str) -> tuple[str, str]:
    for canonical_key, stamps in _FIELD_STAMPS.items():
        if canonical_key not in key:
            continue
        for stamp in stamps:
            value = value.replace(stamp, "")
        return canonical_key, value.strip()
    return key, value


def _extract_labeled_value(detail_row: Tag, label: str) -> tuple[str, str] | None:
    full_text = detail_row.get_text(" ", strip=True)
    value = _clean_value(full_text.replace(label, "", 1).strip().lstrip(":").strip())
    key = _normalize_key(label)
    if key == "outros_numeros":
        return None
    return _canonicalize_field(key, value)


def _extract_detail(detail_row: Tag, data: dict) -> None:
    strong = detail_row.find("strong")
    if strong is None:
        return

    label = strong.get_text(strip=True)
    if "ementa:" in label.lower():
        data["ementa"] = _extract_ementa(detail_row)
        return

    labeled_value = _extract_labeled_value(detail_row, label)
    if labeled_value is not None:
        key, value = labeled_value
        data[key] = value


def _parse_result_row(result_row: Tag) -> dict | None:
    cells = result_row.find_all("td")
    if len(cells) < 2:
        return None

    details_table = cells[1].find("table")
    if details_table is None:
        return None

    data: dict = {"ementa": ""}
    _extract_process_metadata(details_table, data)
    for detail_row in details_table.find_all("tr", class_="ementaClass2"):
        _extract_detail(detail_row, data)
    return data


def _to_dataframe(processes: list[dict]) -> pd.DataFrame:
    dataframe = pd.DataFrame(processes)
    if "ementa" not in dataframe.columns:
        return dataframe
    columns = [column for column in dataframe.columns if column != "ementa"]
    return dataframe[[*columns, "ementa"]]


def _parse_single_page(path: str) -> pd.DataFrame:
    content = _read_html(path)

    soup = BeautifulSoup(content, "html.parser")
    processos: list[dict] = []

    for result_row in soup.find_all("tr", class_="fundocinza1"):
        process = _parse_result_row(result_row)
        if process is not None:
            processos.append(process)

    return _to_dataframe(processos)


_ARVORE_COLUNAS = ["id", "nome", "id_pai", "nivel", "selecionavel", "caminho"]


def parse_arvore(html: str) -> pd.DataFrame:
    """Parseia o HTML de uma arvore eSAJ (classes/assuntos/secoes/varas).

    Le o fragmento retornado por um endpoint ``*TreeSelect.do`` (a arvore
    inteira vem num unico GET) e devolve um ``DataFrame`` achatado, uma linha
    por no, preservando a hierarquia via ``id_pai``/``nivel``/``caminho``.

    A hierarquia e derivada do aninhamento ``<ul>/<li>`` do DOM, nao do
    atributo ``searchValue`` — em arvores reais o ``searchValue`` dos nos
    intermediarios as vezes vem malformado, enquanto o aninhamento e sempre
    confiavel. Um mesmo ``id`` pode aparecer em mais de um ramo; cada
    ocorrencia vira uma linha (a arvore nao e um conjunto de ids unicos).

    Args:
        html: HTML completo retornado pelo endpoint ``*TreeSelect.do``
            (ja decodificado para ``str``).

    Returns:
        pd.DataFrame com as colunas ``id`` (str), ``nome`` (str, caixa
        original), ``id_pai`` (str | None — ``None`` na raiz), ``nivel``
        (int, raiz = 1), ``selecionavel`` (bool — folhas selecionaveis) e
        ``caminho`` (str — nomes dos ancestrais ate o no, juntados por
        `` > ``). Vazio quando o HTML nao contem nos.
    """
    soup = BeautifulSoup(html, "html.parser")
    linhas: list[dict] = []

    for span in soup.select("span.node"):
        node_id = span.get("value") or span.get("searchid") or ""
        classes = span.get("class") or []
        # ``find_parents("li")`` devolve do mais proximo (o <li> do proprio no)
        # ao mais distante (raiz); cada nivel da arvore e exatamente um <li>.
        lis = span.find_parents("li")
        # Nome proprio de cada ancestral: o primeiro ``span.node`` em ordem de
        # documento dentro do <li> e sempre o no daquele <li> (os filhos vem
        # depois, em <ul> aninhados).
        nomes_ancestrais: list[str] = []
        for li in reversed(lis):  # raiz -> no
            no_span = li.find("span", class_="node")
            if no_span is not None:
                nomes_ancestrais.append(no_span.get_text(strip=True))

        id_pai = None
        if len(lis) >= 2:
            pai_span = lis[1].find("span", class_="node")
            if pai_span is not None:
                id_pai = pai_span.get("value") or pai_span.get("searchid") or None

        linhas.append({
            "id": str(node_id),
            "nome": span.get_text(strip=True),
            "id_pai": id_pai,
            "nivel": len(lis),
            "selecionavel": "selectable" in classes,
            "caminho": " > ".join(nomes_ancestrais),
        })

    if not linhas:
        return pd.DataFrame(columns=_ARVORE_COLUNAS)
    return pd.DataFrame(linhas, columns=_ARVORE_COLUNAS)


def cjsg_parse_manager(path: str) -> pd.DataFrame:
    """Parse downloaded cjsg HTML files into a single DataFrame.

    Args:
        path: File or directory containing downloaded HTML files.

    Returns:
        Combined DataFrame. Empty when no files parse successfully.
    """
    if Path(path).is_file():
        return _parse_single_page(path)

    arquivos = [str(f) for f in Path(path).rglob("*.ht*") if f.is_file()]

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
