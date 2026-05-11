"""Downloads raw results from the TJPI jurisprudence search (HTML scraping)."""
import logging
import re
import time

import requests
from tqdm import tqdm

from juscraper.utils.pagination import extract_count_with_cascade

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
    data_min: str = "",
    data_max: str = "",
) -> dict:
    """Build the query-string params dict for the TJPI CJSG search endpoint.

    ``data_min``/``data_max`` are the BFF date filter (ISO ``YYYY-MM-DD``);
    they are wired by ``TJPIScraper.cjsg`` after going through
    ``normalize_datas`` + ``to_iso_date``.
    """
    params = {"q": pesquisa, "page": str(page)}
    if tipo:
        params["tipo"] = tipo
    if relator:
        params["relator"] = relator
    if classe:
        params["classe"] = classe
    if orgao:
        params["orgao"] = orgao
    if data_min:
        params["data_min"] = data_min
    if data_max:
        params["data_max"] = data_max
    return params


def _fetch_page(
    session: requests.Session,
    pesquisa: str,
    page: int = 1,
    tipo: str = "",
    relator: str = "",
    classe: str = "",
    orgao: str = "",
    data_min: str = "",
    data_max: str = "",
    max_retries: int = 3,
) -> str:
    """Fetch a single page of HTML results from the TJPI search."""
    params = build_cjsg_params(
        pesquisa=pesquisa, page=page,
        tipo=tipo, relator=relator, classe=classe, orgao=orgao,
        data_min=data_min, data_max=data_max,
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


_PAGINATION_CSS_SELECTORS: tuple[str, ...] = ("ul.pagination",)
_PAGINATION_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"[?&]page=(\d+)"),
)


def _get_total_pages(html: str) -> int:
    """Extract total number of pages from the TJPI pagination links."""
    n = extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
        use_element_html=True,
        aggregate="max",
        fallback_max_int=False,
    )
    return n if n is not None else 1


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    session: requests.Session | None = None,
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
