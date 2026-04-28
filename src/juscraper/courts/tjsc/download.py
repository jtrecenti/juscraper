"""Downloads raw results from the TJSC jurisprudence search (eproc PHP)."""
import logging
import re
import time
from typing import Optional

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://eproc1g.tjsc.jus.br/eproc/externo_controlador.php"
    "?acao=jurisprudencia@jurisprudencia/listar_resultados"
)
AJAX_URL = (
    "https://eproc1g.tjsc.jus.br/eproc/externo_controlador.php"
    "?acao=jurisprudencia@jurisprudencia/ajax_paginar_resultado"
)
RESULTS_PER_PAGE = 10


def _fetch_page(
    session: requests.Session,
    pesquisa: str,
    page: int = 1,
    campo: str = "E",
    processo: str = "",
    dt_decisao_inicio: str = "",
    dt_decisao_fim: str = "",
    dt_publicacao_inicio: str = "",
    dt_publicacao_fim: str = "",
    num_resultados: int = RESULTS_PER_PAGE,
    max_retries: int = 3,
) -> str:
    """Fetch a single page of results from the TJSC eproc system."""
    data = {
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
    url = AJAX_URL if page > 1 else SEARCH_URL

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(url, data=data, timeout=60)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            return resp.text
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJSC request failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return ""  # unreachable


def _get_total_pages(html: str, per_page: int = RESULTS_PER_PAGE) -> int:
    """Extract total page count from the TJSC response."""
    match = re.search(r"(\d+)\s*documentos?\s*encontrados?", html)
    if match:
        total = int(match.group(1))
        return max(1, (total + per_page - 1) // per_page)
    return 1


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> list:
    """Download raw HTML results from the TJSC jurisprudence search.

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

    def _get_page(pagina_1based):
        html = _fetch_page(session, pesquisa, page=pagina_1based, **kwargs)
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
