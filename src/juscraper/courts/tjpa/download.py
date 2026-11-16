"""
Downloads raw results from the TJPA jurisprudence search.
"""
import json
import time
from datetime import date, timedelta

import requests
from tqdm import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import menor_pagina, paginas_no_intervalo

BASE_URL = "https://jurisprudencia.tjpa.jus.br/bff/api/decisoes/buscar"
SITE_URL = "https://jurisprudencia.tjpa.jus.br"
RESULTS_PER_PAGE = 25

CJSG_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Referer": SITE_URL + "/",
    "Origin": SITE_URL,
}


def _dia_anterior(data_iso: str) -> str:
    """Recua um dia uma data ``YYYY-MM-DD``."""
    return (date.fromisoformat(data_iso) - timedelta(days=1)).isoformat()


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
    """Monta o corpo JSON da busca de jurisprudencia do TJPA.

    O BFF desloca o filtro de data de julgamento em um dia: com
    ``dataJulgamentoInicio`` = ``dataJulgamentoFim`` = D, devolve os acordaos
    cujo ``datajulgamento`` e D+1. O ``datajulgamento`` devolvido e o certo
    (bate com o inicio da sessao escrito no inteiro teor), entao as duas
    datas de julgamento vao ao corpo um dia antes do pedido. O filtro de
    publicacao nao tem o desvio e segue como recebido (#508).
    """
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
        payload["dataJulgamentoInicio"] = _dia_anterior(data_julgamento_inicio)
    if data_julgamento_fim:
        payload["dataJulgamentoFim"] = _dia_anterior(data_julgamento_fim)
    if data_publicacao_inicio:
        payload["dataPublicacaoInicio"] = data_publicacao_inicio
    if data_publicacao_fim:
        payload["dataPublicacaoFim"] = data_publicacao_fim

    return payload


def post_cjsg(request_fn: RequestFn, payload: dict) -> requests.Response:
    """Send the TJPA CJSG search request via ``request_fn``.

    Single source of truth for the request shape (URL + body serialization
    with ``ensure_ascii=False`` + headers). Both ``cjsg_download_manager``
    and the capture script in ``tests/fixtures/capture/tjpa.py`` call this
    helper so a change to body/headers can't drift silently.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return request_fn("POST", BASE_URL, data=body, headers=CJSG_HEADERS, perfil="cjsg")


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

    # A menor página pedida sai primeiro, porque traz o total; as demais, na
    # ordem pedida, uma vez cada, e as além do total vão para o log. O BFF
    # responde a uma página além do total com a última, sem erro.
    primeira = menor_pagina(paginas)
    first = _get_page(primeira)
    n_pags = max(1, first.get("data", {}).get("totalPages", 1))
    resultados = []
    for pagina in tqdm(paginas_no_intervalo(paginas, n_pags, tribunal="TJPA"), desc="Baixando páginas TJPA"):
        if pagina == primeira:
            resultados.append(first)
            continue
        resultados.append(_get_page(pagina))
    return resultados
