"""
Functions for downloading specific data from the Datajud API.
"""
import logging
from typing import Any

import requests

from ...core.avisos import avisar
from ...core.http import RequestFn
from ...utils.cnj import clean_cnj
from ...utils.logging_cfg import redact_headers

logger = logging.getLogger(__name__)

# Quando a chamada falha com ``HTTP 504`` ou ``Timeout``, ``call_datajud_api``
# refaz a requisicao 1 unica vez com ``size`` reduzido pelo fator abaixo
# (``new_size = max(size // FALLBACK_DIVISOR, FALLBACK_MIN_SIZE)``). 504
# acontece quando o servidor demora mais que o timeout do gateway (~60s);
# uma reducao agressiva (4x, nao 2x) tem mais chance de passar na segunda
# tentativa, evitando a custosa cascata "5000 -> 2500 -> 1250" de 3
# tentativas perdidas.
FALLBACK_DIVISOR = 4
FALLBACK_MIN_SIZE = 100
FALLBACK_RETRY_STATUS = {504}

# Status que o perfil ``"busca"`` do ``DatajudScraper`` repete com espera, antes
# de qualquer fallback: o servidor pediu para tentar de novo mais tarde. O 429
# vem com ``es_rejected_execution_exception`` quando a fila de busca do cluster
# enche, sinal de sobrecarga e não da consulta. O 500 fica de fora, porque costuma ser erro da
# consulta, e o 504 tem o fallback de ``size`` acima.
STATUS_REPETIVEIS = frozenset({429, 502, 503})


def build_listar_processos_payload(
    *,
    numero_processo: str | list[str] | None = None,
    ano_ajuizamento: int | None = None,
    classe: str | None = None,
    assunto: list[str] | None = None,
    data_ajuizamento_inicio: str | None = None,
    data_ajuizamento_fim: str | None = None,
    movimentos_codigo: list[int] | None = None,
    orgao_julgador: str | None = None,
    query: dict[str, Any] | None = None,
    mostrar_movs: bool = False,
    tamanho_pagina: int = 5000,
    search_after: list[Any] | None = None,
) -> dict[str, Any]:
    """Construir o body Elasticsearch para ``DatajudScraper.listar_processos``.

    Dois caminhos:

    1. **Amigavel** (``query`` is ``None``): reune ``must_conditions`` na
       ordem canonica abaixo e monta ``query.bool.must`` (ou ``match_all``
       se nenhum filtro). A ordem importa — os contratos offline em
       ``tests/datajud/test_listar_processos_*_contract.py`` validam o body
       inteiro via ``json_params_matcher``.

       Ordem canonica das ``must_conditions``:

       1. ``numero_processo`` -> ``terms`` em ``numeroProcesso``
       2. ``ano_ajuizamento`` ou ``data_ajuizamento_inicio/fim`` -> ``bool.should``
          com 2 ``range`` em ``dataAjuizamento`` (ISO + compacto, refs #51).
          Mutuamente exclusivos no schema (validator); aqui ``ano_ajuizamento``
          tem precedencia se ambos chegarem.
       3. ``classe`` -> ``match`` em ``classe.codigo``
       4. ``assunto`` -> ``terms`` em ``assuntos.codigo``
       5. ``movimentos_codigo`` -> ``terms`` em ``movimentos.codigo``
       6. ``orgao_julgador`` -> ``match`` em ``orgaoJulgador.nome``

    2. **Override** (``query`` is not ``None``): bypassa toda a montagem de
       ``must_conditions`` e usa ``query`` literalmente como a chave
       ``query`` do payload Elasticsearch. O resto do payload
       (``size``/``sort``/``_source``/``search_after``) continua sendo
       construido pela biblioteca. O schema garante que os filtros
       amigaveis nao chegam aqui junto com ``query``, mas o builder em si
       e defensivo: ignora silenciosamente qualquer filtro amigavel quando
       ``query`` e fornecido.

    Em ambos os caminhos, ``mostrar_movs`` controla ``_source``,
    ``tamanho_pagina`` -> ``size`` e ``search_after`` -> deep pagination.
    """
    if query is not None:
        query_values: dict[str, Any] = query
    else:
        query_values = _build_query_amigavel(
            numero_processo=numero_processo,
            ano_ajuizamento=ano_ajuizamento,
            classe=classe,
            assunto=assunto,
            data_ajuizamento_inicio=data_ajuizamento_inicio,
            data_ajuizamento_fim=data_ajuizamento_fim,
            movimentos_codigo=movimentos_codigo,
            orgao_julgador=orgao_julgador,
        )

    payload: dict[str, Any] = {
        "query": query_values,
        "size": tamanho_pagina,
        "track_total_hits": True,
        "sort": [{"id.keyword": "asc"}],
    }
    if search_after is not None:
        payload["search_after"] = search_after
    if mostrar_movs:
        payload["_source"] = True
    else:
        payload["_source"] = {"excludes": ["movimentacoes", "movimentos"]}
    return payload


def _build_query_amigavel(
    *,
    numero_processo: str | list[str] | None,
    ano_ajuizamento: int | None,
    classe: str | None,
    assunto: list[str] | None,
    data_ajuizamento_inicio: str | None,
    data_ajuizamento_fim: str | None,
    movimentos_codigo: list[int] | None,
    orgao_julgador: str | None,
) -> dict[str, Any]:
    """Monta ``query.bool.must`` a partir dos filtros amigaveis."""
    must_conditions: list[dict[str, Any]] = []
    if numero_processo:
        nproc = [numero_processo] if isinstance(numero_processo, str) else list(numero_processo)
        nproc = [clean_cnj(n) for n in nproc]
        must_conditions.append({"terms": {"numeroProcesso": nproc}})
    if ano_ajuizamento:
        date_range_iso = {
            "gte": f"{ano_ajuizamento}-01-01",
            "lte": f"{ano_ajuizamento}-12-31",
        }
        date_range_compact = {
            "gte": f"{ano_ajuizamento}0101000000",
            "lte": f"{ano_ajuizamento}1231235959",
        }
        must_conditions.append({
            "bool": {
                "should": [
                    {"range": {"dataAjuizamento": date_range_iso}},
                    {"range": {"dataAjuizamento": date_range_compact}},
                ],
                "minimum_should_match": 1,
            }
        })
    elif data_ajuizamento_inicio is not None or data_ajuizamento_fim is not None:
        # Mesmo padrao dual-format do ``ano_ajuizamento`` (refs #51): TRF3/TRF4
        # armazenam ``dataAjuizamento`` no formato compacto ``YYYYMMDDhhmmss``
        # e ignoram ``range`` ISO-only. ``minimum_should_match: 1`` cobre os
        # dois universos.
        range_iso: dict[str, str] = {}
        range_compact: dict[str, str] = {}
        if data_ajuizamento_inicio is not None:
            range_iso["gte"] = data_ajuizamento_inicio
            range_compact["gte"] = (
                data_ajuizamento_inicio.replace("-", "") + "000000"
            )
        if data_ajuizamento_fim is not None:
            range_iso["lte"] = data_ajuizamento_fim
            range_compact["lte"] = (
                data_ajuizamento_fim.replace("-", "") + "235959"
            )
        must_conditions.append({
            "bool": {
                "should": [
                    {"range": {"dataAjuizamento": range_iso}},
                    {"range": {"dataAjuizamento": range_compact}},
                ],
                "minimum_should_match": 1,
            }
        })
    if classe:
        must_conditions.append({"match": {"classe.codigo": classe}})
    if assunto:
        # ``assuntos.codigo`` e a chave do payload Elasticsearch (campo do
        # backend). O parametro Python e ``assunto`` (singular, refs #232).
        must_conditions.append({"terms": {"assuntos.codigo": assunto}})
    if movimentos_codigo:
        must_conditions.append({"terms": {"movimentos.codigo": list(movimentos_codigo)}})
    if orgao_julgador:
        must_conditions.append({"match": {"orgaoJulgador.nome": orgao_julgador}})

    if must_conditions:
        return {"bool": {"must": must_conditions}}
    return {"match_all": {}}


def build_contar_processos_payload(
    *,
    numero_processo: str | list[str] | None = None,
    ano_ajuizamento: int | None = None,
    classe: str | None = None,
    assunto: list[str] | None = None,
    data_ajuizamento_inicio: str | None = None,
    data_ajuizamento_fim: str | None = None,
    movimentos_codigo: list[int] | None = None,
    orgao_julgador: str | None = None,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Body Elasticsearch para ``DatajudScraper.contar_processos``.

    Reutiliza o mesmo conjunto de filtros de
    :func:`build_listar_processos_payload`, mas com ``size=0`` e
    ``track_total_hits=True`` — nao baixa documento nenhum, apenas o
    ``hits.total`` (``value`` + ``relation``). Sem ``sort`` nem
    ``_source`` (nao ha paginacao).

    Aceita os mesmos filtros amigaveis de ``listar_processos``
    (``data_ajuizamento_*``, ``movimentos_codigo``, ``orgao_julgador``)
    e o escape-hatch ``query`` (override total da query Elasticsearch,
    mutuamente exclusivo com os filtros amigaveis pelo schema). Os
    filtros sao construidos pelo mesmo helper interno
    :func:`_build_query_amigavel` usado por ``listar_processos`` —
    capture e producao falham juntos quando o body real muda.
    """
    if query is not None:
        query_values: dict[str, Any] = query
    else:
        query_values = _build_query_amigavel(
            numero_processo=numero_processo,
            ano_ajuizamento=ano_ajuizamento,
            classe=classe,
            assunto=assunto,
            data_ajuizamento_inicio=data_ajuizamento_inicio,
            data_ajuizamento_fim=data_ajuizamento_fim,
            movimentos_codigo=movimentos_codigo,
            orgao_julgador=orgao_julgador,
        )

    return {
        "query": query_values,
        "size": 0,
        "track_total_hits": True,
    }


def call_datajud_api(
    base_url: str,
    alias: str,
    api_key: str,
    requisitar: RequestFn,
    query_payload: dict[str, Any],
    verbose: bool = False,
) -> dict[str, Any]:
    """Faz a busca ``_search`` de um alias do DataJud e devolve o JSON da resposta.

    Args:
        base_url: URL base da API (por exemplo, https://api-publica.datajud.cnj.jus.br).
        alias: Alias do índice do tribunal (por exemplo, api_publica_tjsp).
        api_key: Chave da API.
        requisitar: ``HTTPScraper._request_with_retry`` já ligado ao perfil
            ``"busca"``. Dele vêm o ``timeout`` e as novas tentativas em
            :data:`STATUS_REPETIVEIS` (429, 502 e 503), com espera pelo
            ``Retry-After`` numérico ou pelo backoff exponencial do perfil.
        query_payload: Body Elasticsearch.
        verbose: Se ``True``, registra URL, payload e status no log.

    Returns:
        O JSON da resposta.

    Raises:
        juscraper.core.exceptions.RetryExhaustedError: Status repetível em
            todas as tentativas do perfil.
        requests.HTTPError: Status de erro que não se repete (401, 500, 504
            depois do fallback), com a resposta em ``.response``.
        requests.Timeout: Timeout, também depois do fallback.
        requests.RequestException: Erro de conexão ou corpo que não é JSON.

    Note:
        Em ``HTTP 504`` ou ``Timeout`` (gateway saturado), refaz a busca **uma
        vez** com ``size`` reduzido por ``FALLBACK_DIVISOR``, mutando
        ``query_payload["size"]`` no lugar: o caller lê ``query_payload["size"]``
        na heurística de última página (``len(hits) < query_payload["size"]``)
        para não parar antes do tempo. Emite ``UserWarning`` com o novo size.
        Se ``size`` já está no mínimo ou a nova busca também falha, a exceção
        sobe para o caller.
    """
    api_url = f"{base_url}/{alias}/_search"
    headers = {
        "Authorization": f"APIKey {api_key}",
        "Content-Type": "application/json"
    }

    if verbose:
        logger.info("Calling Datajud API: %s", api_url)
        logger.debug("Headers: %s", redact_headers(headers))
        logger.debug("Payload: %s", query_payload)

    def _do_post() -> dict[str, Any]:
        response = requisitar("POST", api_url, json=query_payload, headers=headers)
        if verbose:
            logger.debug("Response Status Code: %s", response.status_code)
        data: dict[str, Any] = response.json()
        return data

    try:
        return _do_post()
    except (requests.exceptions.HTTPError, requests.exceptions.Timeout) as exc:
        if not (_e_sobrecarga(exc) and _reduzir_size(alias, query_payload)):
            raise
    return _do_post()


def _e_sobrecarga(exc: BaseException) -> bool:
    """Diz se a falha é do gateway saturado (504 ou timeout), que o fallback de ``size`` trata."""
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return status in FALLBACK_RETRY_STATUS


def _reduzir_size(alias: str, query_payload: dict[str, Any]) -> bool:
    """Reduz ``query_payload["size"]`` por ``FALLBACK_DIVISOR`` para a nova busca após 504/timeout.

    Muta ``query_payload["size"]`` no lugar para que o caller leia o size
    efetivo na heurística de última página (``len(hits) < query_payload['size']``)
    em ``client.py:_iter_process_pages``. Devolve ``False``, sem mexer no
    payload, quando o ``size`` já está no mínimo e reduzir não ajuda.
    """
    original_size = query_payload.get("size")
    if not isinstance(original_size, int) or original_size <= FALLBACK_MIN_SIZE:
        return False
    new_size = max(original_size // FALLBACK_DIVISOR, FALLBACK_MIN_SIZE)
    avisar(
        f"DataJud: 504/timeout em ``size={original_size}`` no alias "
        f"{alias!r}. Refazendo com ``size={new_size}`` (1 retry).",
        UserWarning,
    )
    logger.warning(
        "DataJud: 504/timeout em size=%d (alias %s); refazendo com size=%d.",
        original_size, alias, new_size,
    )
    query_payload["size"] = new_size
    return True
