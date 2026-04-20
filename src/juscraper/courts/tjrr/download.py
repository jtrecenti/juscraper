"""Downloads raw results from the TJRR jurisprudence search (JSF/PrimeFaces)."""
import logging
import re
import time
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.tjrr.jus.br/index.xhtml"
RESULTS_PER_PAGE = 10


def _extract_cdata(xml_text: str) -> str:
    """Extract HTML content from a PrimeFaces AJAX XML response."""
    if not xml_text.startswith("<?xml"):
        return xml_text
    cdata_matches: list[str] = re.findall(r"<!\[CDATA\[(.*?)\]\]>", xml_text, re.DOTALL)
    for cdata in cdata_matches:
        if "resultados" in cdata:
            return cdata
    # If no match with 'resultados', return the largest CDATA block
    if cdata_matches:
        return max(cdata_matches, key=len)
    return xml_text


def _get_viewstate(session: requests.Session) -> str:
    """Fetch the initial page and extract the JSF ViewState."""
    resp = session.get(BASE_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    vs_input = soup.find("input", {"name": "javax.faces.ViewState"})
    if not vs_input:
        raise RuntimeError("Could not find ViewState on TJRR page.")
    return str(vs_input["value"])


def _search(
    session: requests.Session,
    viewstate: str,
    pesquisa: str,
    relator: str = "",
    data_inicio: str = "",
    data_fim: str = "",
    orgao_julgador: list | None = None,
    especie: list | None = None,
    max_retries: int = 3,
) -> str:
    """Submit the search form and return the HTML response."""
    data: dict = {
        "menuinicial": "menuinicial",
        "menuinicial:j_idt28": pesquisa,
        "menuinicial:numProcesso": "",
        "menuinicial:datainicial_input": data_inicio,
        "menuinicial:datafinal_input": data_fim,
        "menuinicial:j_idt67": relator,
        "javax.faces.ViewState": viewstate,
        "menuinicial:j_idt30": "",
    }
    if orgao_julgador:
        for oj in orgao_julgador:
            data.setdefault("menuinicial:tipoOrgaoList", []).append(oj)
    if especie:
        for esp in especie:
            data.setdefault("menuinicial:tipoEspecieList", []).append(esp)

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, data=data, timeout=60)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJRR request failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return ""  # unreachable


def _get_total_pages(html: str) -> int:
    """Extract total pages from the PrimeFaces paginator."""
    match = re.search(r"\((\d+) of (\d+)\)", html)
    if match:
        return int(match.group(2))
    return 1


def _paginate(
    session: requests.Session,
    html: str,
    page: int,
    max_retries: int = 3,
) -> str:
    """Navigate to a specific page using PrimeFaces AJAX pagination."""
    soup = BeautifulSoup(html, "html.parser")
    vs_input = soup.find("input", {"name": "javax.faces.ViewState"})
    if not vs_input:
        raise RuntimeError("Could not find ViewState for pagination.")

    viewstate = vs_input["value"]
    rows = RESULTS_PER_PAGE
    first = (page - 1) * rows

    data = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "formPesquisa:j_idt159:dataTablePesquisa",
        "javax.faces.partial.execute": "formPesquisa:j_idt159:dataTablePesquisa",
        "javax.faces.partial.render": "formPesquisa:j_idt159:dataTablePesquisa",
        "formPesquisa:j_idt159:dataTablePesquisa_pagination": "true",
        "formPesquisa:j_idt159:dataTablePesquisa_first": str(first),
        "formPesquisa:j_idt159:dataTablePesquisa_rows": str(rows),
        "formPesquisa": "formPesquisa",
        "javax.faces.ViewState": viewstate,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, data=data, timeout=60)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return _extract_cdata(resp.text)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJRR pagination failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return ""  # unreachable


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> list:
    """Download raw HTML results from the TJRR jurisprudence search.

    Returns a list of raw HTML strings (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        session: Optional requests.Session to reuse.
        **kwargs: Additional filter parameters.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    viewstate = _get_viewstate(session)
    first_html = _search(session, viewstate, pesquisa, **kwargs)
    time.sleep(1)

    if paginas is None:
        resultados = [first_html]
        n_pags = _get_total_pages(first_html)
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJRR"):
                html = _paginate(session, first_html, pagina)
                resultados.append(html)
                time.sleep(1)
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJRR"):
        if pagina_1based == 1:
            resultados.append(first_html)
        else:
            html = _paginate(session, first_html, pagina_1based)
            resultados.append(html)
            time.sleep(1)
    return resultados
