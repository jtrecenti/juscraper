"""Downloads raw results from the TJPI jurisprudence search (HTML scraping)."""
import re
import time

from tqdm import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import extract_count_with_cascade

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
    *,
    request_fn: RequestFn,
    sleep_time: float = 1.0,
    **kwargs,
) -> list:
    """Download raw HTML pages from the TJPI jurisprudence search.

    Returns a list of raw HTML strings (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJPIScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx.
        sleep_time: Delay (em segundos) entre páginas. Default 1.0; o client
            normalmente passa ``self.sleep_time`` herdado de ``HTTPScraper``.
        **kwargs: Additional filter parameters (tipo, relator, classe, orgao).
    """
    def _get_page(pagina_1based: int) -> str:
        params = build_cjsg_params(pesquisa=pesquisa, page=pagina_1based, **kwargs)
        resp = request_fn("GET", BASE_URL, params=params, timeout=30)
        resp.encoding = "utf-8"
        html = resp.text
        return html

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        n_pags = _get_total_pages(first)
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJPI"):
                time.sleep(sleep_time)
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJPI"):
        if resultados:
            time.sleep(sleep_time)
        resultados.append(_get_page(pagina_1based))
    return resultados
