"""Downloads raw results from the TJSC jurisprudence search (eproc PHP)."""
import re
import time

from tqdm import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import extract_count_with_cascade

SEARCH_URL = (
    "https://eproc1g.tjsc.jus.br/eproc/externo_controlador.php"
    "?acao=jurisprudencia@jurisprudencia/listar_resultados"
)
AJAX_URL = (
    "https://eproc1g.tjsc.jus.br/eproc/externo_controlador.php"
    "?acao=jurisprudencia@jurisprudencia/ajax_paginar_resultado"
)
RESULTS_PER_PAGE = 10


def build_cjsg_form_body(
    pesquisa: str,
    page: int = 1,
    campo: str = "E",
    processo: str = "",
    dt_decisao_inicio: str = "",
    dt_decisao_fim: str = "",
    dt_publicacao_inicio: str = "",
    dt_publicacao_fim: str = "",
    num_resultados: int = RESULTS_PER_PAGE,
) -> dict:
    """Build the form-encoded body for the TJSC CJSG eproc endpoint."""
    return {
        "txtPesquisa": pesquisa,
        "rdoCampo": campo,
        "txtProcesso": processo,
        "dtDecisaoInicio": dt_decisao_inicio,
        "dtDecisaoFim": dt_decisao_fim,
        "dtPublicacaoInicio": dt_publicacao_inicio,
        "dtPublicacaoFim": dt_publicacao_fim,
        "hdnPaginaAtual": str(page),
        "numResultadosPorPagina": str(num_resultados),
    }


def cjsg_url_for_page(page: int) -> str:
    """Return the TJSC CJSG endpoint URL for a given 1-based page number."""
    return AJAX_URL if page > 1 else SEARCH_URL


_PAGINATION_CSS_SELECTORS: tuple[str, ...] = ("h2.mb-0",)
_PAGINATION_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(\d+)\s*documentos?\s*encontrados?", re.IGNORECASE),
)


def _get_total_pages(html: str, per_page: int = RESULTS_PER_PAGE) -> int:
    """Extract total page count from the TJSC response."""
    total = extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
        fallback_max_int=False,
    )
    if total is None:
        return 1
    return max(1, (total + per_page - 1) // per_page)


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    **kwargs,
) -> list:
    """Download raw HTML results from the TJSC jurisprudence search.

    Returns a list of raw HTML strings (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJSCScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx.
        **kwargs: Additional filter parameters.
    """
    def _get_page(pagina_1based: int) -> str:
        data = build_cjsg_form_body(pesquisa=pesquisa, page=pagina_1based, **kwargs)
        url = cjsg_url_for_page(pagina_1based)
        resp = request_fn("POST", url, data=data, timeout=60)
        resp.encoding = resp.apparent_encoding
        html = resp.text
        time.sleep(1)
        return html

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        n_pags = _get_total_pages(first)
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJSC"):
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJSC"):
        resultados.append(_get_page(pagina_1based))
    return resultados
