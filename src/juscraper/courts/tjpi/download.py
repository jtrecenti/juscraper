"""Downloads raw results from the TJPI jurisprudence search (HTML scraping)."""
import logging
import re
import time
from typing import Optional

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.tjpi.jus.br/jurisprudences/search"
RESULTS_PER_PAGE = 25


def build_cjsg_params(
    pesquisa: str,
    page: int = 1,
    tipo: str = "",
    relator: str = "",
    classe: str = "",
    orgao: str = "",
) -> dict:
    """Build the query-string params dict for the TJPI CJSG search endpoint."""
    params = {"q": pesquisa, "page": str(page)}
    if tipo:
        params["tipo"] = tipo
    if relator:
        params["relator"] = relator
    if classe:
        params["classe"] = classe
    if orgao:
        params["orgao"] = orgao
    return params


def _fetch_page(
    session: requests.Session,
    pesquisa: str,
    page: int = 1,
    tipo: str = "",
    relator: str = "",
    classe: str = "",
    orgao: str = "",
    max_retries: int = 3,
) -> str:
    """Fetch a single page of HTML results from the TJPI search."""
    params = build_cjsg_params(
        pesquisa=pesquisa, page=page,
        tipo=tipo, relator=relator, classe=classe, orgao=orgao,
    )

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJPI request failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return ""  # unreachable


def _get_total_pages(html: str) -> int:
    """Extract total number of pages from the TJPI pagination links."""
    # Find the last page number from pagination links (e.g. page=5515 in the » button)
    matches = re.findall(r'[?&]page=(\d+)', html)
    if matches:
        return max(int(m) for m in matches)
    return 1


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> list:
    """Download raw HTML pages from the TJPI jurisprudence search.

    Returns a list of raw HTML strings (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        session: Optional requests.Session to reuse.
        **kwargs: Additional filter parameters (tipo, relator, classe, orgao).
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def _get_page(pagina_1based):
        html = _fetch_page(session, pesquisa, page=pagina_1based, **kwargs)
        time.sleep(1)
        return html

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        n_pags = _get_total_pages(first)
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJPI"):
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJPI"):
        resultados.append(_get_page(pagina_1based))
    return resultados
