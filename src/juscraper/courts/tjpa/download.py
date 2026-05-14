"""
Downloads raw results from the TJPA jurisprudence search.
"""
import json
import logging
import time

import requests
from tqdm import tqdm

from juscraper.core.http import RequestFn

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.tjpa.jus.br/bff/api/decisoes/buscar"
SITE_URL = "https://jurisprudencia.tjpa.jus.br"
RESULTS_PER_PAGE = 25

CJSG_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Referer": SITE_URL + "/",
    "Origin": SITE_URL,
}


def build_cjsg_payload(
    pesquisa: str,
    pagina_0based: int,
    size: int = RESULTS_PER_PAGE,
    origem: list | None = None,
    tipo: list | None = None,
    relator: str | None = None,
    orgao_julgador_colegiado: str | None = None,
    classe: str | None = None,
    assunto: str | None = None,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    sort_by: str = "datajulgamento",
    sort_order: str = "desc",
    query_type: str = "free",
    query_scope: str = "ementa",
) -> dict:
    """Build the JSON payload for the TJPA search API."""
    if origem is None:
        origem = ["tribunal de justiça do estado do pará"]
    if tipo is None:
        tipo = ["acórdão", "decisão monocrática"]

    payload = {
        "query": pesquisa,
        "queryType": query_type,
        "queryScope": query_scope,
        "origem": origem,
        "tipo": tipo,
        "page": pagina_0based,
        "size": size,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }

    if relator:
        payload["relator"] = relator
    if orgao_julgador_colegiado:
        payload["orgaoJulgadorColegiado"] = orgao_julgador_colegiado
    if classe:
        payload["classe"] = classe
    if assunto:
        payload["assunto"] = assunto
    if data_julgamento_inicio:
        payload["dataJulgamentoInicio"] = data_julgamento_inicio
    if data_julgamento_fim:
        payload["dataJulgamentoFim"] = data_julgamento_fim
    if data_publicacao_inicio:
        payload["dataPublicacaoInicio"] = data_publicacao_inicio
    if data_publicacao_fim:
        payload["dataPublicacaoFim"] = data_publicacao_fim

    return payload


def post_cjsg(request_fn: RequestFn, payload: dict, *, timeout: int = 30) -> requests.Response:
    """Send the TJPA CJSG search request via ``request_fn``.

    Single source of truth for the request shape (URL + body serialization
    with ``ensure_ascii=False`` + headers). Both ``cjsg_download_manager``
    and the capture script in ``tests/fixtures/capture/tjpa.py`` call this
    helper so a change to body/headers can't drift silently.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return request_fn("POST", BASE_URL, data=body, headers=CJSG_HEADERS, timeout=timeout)


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    **kwargs,
) -> list:
    """
    Downloads raw results from the TJPA jurisprudence search (multiple pages).
    Returns a list of raw JSON responses.

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
        request_fn: HTTP callable que aplica retry + ``raise_for_status``.
            Em uso normal e ``TJPAScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``).
        **kwargs: Additional parameters forwarded to ``build_cjsg_payload``.
    """
    def _get_page(pagina_1based):
        payload = build_cjsg_payload(pesquisa, pagina_0based=pagina_1based - 1, **kwargs)
        resp = post_cjsg(request_fn, payload)
        resp.encoding = "utf-8"
        data: dict = resp.json()
        time.sleep(1)
        return data

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        total_pages = first.get("data", {}).get("totalPages", 1)
        if total_pages > 1:
            logger.info("TJPA: %d pages found. Downloading all...", total_pages)
            for pagina in tqdm(range(2, total_pages + 1), desc="Baixando páginas TJPA"):
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando páginas TJPA"):
        resultados.append(_get_page(pagina_1based))
    return resultados
