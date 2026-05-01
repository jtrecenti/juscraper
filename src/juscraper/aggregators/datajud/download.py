"""
Functions for downloading specific data from the Datajud API.
"""
import logging
import warnings
from typing import Any, Callable, Dict, List, Optional, Union

import requests

from ...utils.cnj import clean_cnj

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


def build_listar_processos_payload(
    *,
    numero_processo: Optional[Union[str, List[str]]] = None,
    ano_ajuizamento: Optional[int] = None,
    classe: Optional[str] = None,
    assuntos: Optional[List[str]] = None,
    data_ajuizamento_inicio: Optional[str] = None,
    data_ajuizamento_fim: Optional[str] = None,
    movimentos_codigo: Optional[List[int]] = None,
    orgao_julgador: Optional[str] = None,
    query: Optional[Dict[str, Any]] = None,
    mostrar_movs: bool = False,
    tamanho_pagina: int = 5000,
    search_after: Optional[List[Any]] = None,
) -> Dict[str, Any]:
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
       4. ``assuntos`` -> ``terms`` em ``assuntos.codigo``
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
        query_values: Dict[str, Any] = query
    else:
        query_values = _build_query_amigavel(
            numero_processo=numero_processo,
            ano_ajuizamento=ano_ajuizamento,
            classe=classe,
            assuntos=assuntos,
            data_ajuizamento_inicio=data_ajuizamento_inicio,
            data_ajuizamento_fim=data_ajuizamento_fim,
            movimentos_codigo=movimentos_codigo,
            orgao_julgador=orgao_julgador,
        )

    payload: Dict[str, Any] = {
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
    numero_processo: Optional[Union[str, List[str]]],
    ano_ajuizamento: Optional[int],
    classe: Optional[str],
    assuntos: Optional[List[str]],
    data_ajuizamento_inicio: Optional[str],
    data_ajuizamento_fim: Optional[str],
    movimentos_codigo: Optional[List[int]],
    orgao_julgador: Optional[str],
) -> Dict[str, Any]:
    """Monta ``query.bool.must`` a partir dos filtros amigaveis."""
    must_conditions: List[Dict[str, Any]] = []
    if numero_processo:
        if isinstance(numero_processo, str):
            nproc = [numero_processo]
        else:
            nproc = list(numero_processo)
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
        range_iso: Dict[str, str] = {}
        range_compact: Dict[str, str] = {}
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
        must_conditions.append({"match": {"classe.codigo": str(classe)}})
    if assuntos:
        must_conditions.append({"terms": {"assuntos.codigo": assuntos}})
    if movimentos_codigo:
        must_conditions.append({"terms": {"movimentos.codigo": list(movimentos_codigo)}})
    if orgao_julgador:
        must_conditions.append({"match": {"orgaoJulgador.nome": orgao_julgador}})

    if must_conditions:
        return {"bool": {"must": must_conditions}}
    return {"match_all": {}}


def build_contar_processos_payload(
    *,
    numero_processo: Optional[Union[str, List[str]]] = None,
    ano_ajuizamento: Optional[int] = None,
    classe: Optional[str] = None,
    assuntos: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Body Elasticsearch para ``DatajudScraper.contar_processos``.

    Reutiliza o mesmo conjunto de filtros de
    :func:`build_listar_processos_payload`, mas com ``size=0`` e
    ``track_total_hits=True`` — não baixa documento nenhum, apenas o
    ``hits.total`` (``value`` + ``relation``). Sem ``sort`` nem
    ``_source`` (não há paginação).
    """
    must_conditions: List[Dict[str, Any]] = []
    if numero_processo:
        if isinstance(numero_processo, str):
            nproc = [numero_processo]
        else:
            nproc = list(numero_processo)
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
    if classe:
        must_conditions.append({"match": {"classe.codigo": str(classe)}})
    if assuntos:
        must_conditions.append({"terms": {"assuntos.codigo": assuntos}})

    if must_conditions:
        query_values: Dict[str, Any] = {"bool": {"must": must_conditions}}
    else:
        query_values = {"match_all": {}}

    return {
        "query": query_values,
        "size": 0,
        "track_total_hits": True,
    }


def call_datajud_api(
    base_url: str,
    alias: str,
    api_key: str,
    session: requests.Session,
    query_payload: Dict[str, Any],
    verbose: bool = False,
    timeout: int = 60  # seconds
) -> Optional[Dict[str, Any]]:
    """
    Calls the Datajud API for a given alias with a specific query.

    Args:
        base_url (str): The base URL of Datajud API (e.g. https://api-publica.datajud.cnj.jus.br).
        alias (str): The API alias for the specific tribunal/service (e.g. api_publica_tjsp).
        api_key (str): The API key for authorization.
        session (requests.Session): The requests session to use.
        query_payload (Dict[str, Any]): The Elasticsearch query payload.
        verbose (bool): If True, logs more details about the request.
        timeout (int): Request timeout in seconds.

    Returns:
        Optional[Dict[str, Any]]: The JSON response from the API as a dictionary,
                                   or None if the request fails or returns an error.

    Note:
        Em caso de falha, retorna None e loga o erro via logger.error. O caller
        (`_listar_processos_por_alias` em client.py) emite um unico
        `warnings.warn(UserWarning)` agregado por alias quando detecta None,
        evitando spam de warnings em paginacao longa com API instavel.

        Em ``HTTP 504``/``Timeout`` (gateway saturado), faz **1 retry**
        automatico com ``size`` reduzido por ``FALLBACK_DIVISOR`` (default 4),
        mutando ``query_payload["size"]`` em place — o caller le
        ``query_payload["size"]`` na heuristica de "ultima pagina"
        (``len(hits) < query_payload["size"]``) para nao parar antes do tempo
        quando o fallback rebaixou o size. Emite ``UserWarning`` informando o
        novo size. Se o retry tambem falhar, segue o fluxo normal (return None).
    """
    api_url = f"{base_url}/{alias}/_search"
    headers = {
        "Authorization": f"APIKey {api_key}",
        "Content-Type": "application/json"
    }

    if verbose:
        logger.info("Calling Datajud API: %s", api_url)
        # Redact key in log for security
        logger.debug(
            "Headers: {'Authorization': 'APIKey [REDACTED]',"
            "'Content-Type': 'application/json'}"
        )
        logger.debug("Payload: %s", query_payload)

    def _do_post() -> Optional[Dict[str, Any]]:
        response = session.post(api_url, json=query_payload, headers=headers, timeout=timeout)
        if verbose:
            logger.debug("Response Status Code: %s", response.status_code)
        response.raise_for_status()
        data: Dict[str, Any] = response.json()
        return data

    def _is_overload(exc: BaseException) -> bool:
        if isinstance(exc, requests.exceptions.Timeout):
            return True
        if isinstance(exc, requests.exceptions.HTTPError):
            status = getattr(getattr(exc, "response", None), "status_code", None)
            return status in FALLBACK_RETRY_STATUS
        return False

    try:
        return _do_post()
    except (requests.exceptions.HTTPError, requests.exceptions.Timeout) as exc:
        if _is_overload(exc):
            return _retry_with_reduced_size(api_url, alias, query_payload, _do_post, exc)
        _log_http_error(api_url, exc)
        return None
    except requests.exceptions.RequestException as exc:
        logger.error("Request failed for Datajud API (%s): %s", api_url, exc)
        return None
    except ValueError as exc:  # Includes JSONDecodeError if response is not valid JSON
        logger.error("Failed to decode JSON response from Datajud API (%s): %s", api_url, exc)
        return None
    except Exception as exc:
        logger.error("An unexpected error occurred calling Datajud API (%s): %s", api_url, exc)
        return None


def _retry_with_reduced_size(
    api_url: str,
    alias: str,
    query_payload: Dict[str, Any],
    do_post: Callable[[], Optional[Dict[str, Any]]],
    original_exc: BaseException,
) -> Optional[Dict[str, Any]]:
    """1 retry com ``size`` reduzido por ``FALLBACK_DIVISOR`` apos 504/timeout.

    Muta ``query_payload["size"]`` em place para que o caller leia o size
    efetivo na heuristica de ultima pagina (``len(hits) < query_payload['size']``)
    em ``client.py:_listar_processos_por_alias``. Retorna ``None`` em qualquer
    falha do retry, alinhado ao contrato de ``call_datajud_api``.
    """
    original_size = query_payload.get("size")
    if not isinstance(original_size, int) or original_size <= FALLBACK_MIN_SIZE:
        _log_http_error(api_url, original_exc)
        return None
    new_size = max(original_size // FALLBACK_DIVISOR, FALLBACK_MIN_SIZE)
    if new_size >= original_size:
        _log_http_error(api_url, original_exc)
        return None
    warnings.warn(
        f"DataJud: 504/timeout em ``size={original_size}`` no alias "
        f"{alias!r}. Refazendo com ``size={new_size}`` (1 retry).",
        UserWarning,
        stacklevel=4,
    )
    logger.warning(
        "DataJud: 504/timeout em size=%d (alias %s); refazendo com size=%d.",
        original_size, alias, new_size,
    )
    query_payload["size"] = new_size
    try:
        return do_post()
    except (requests.exceptions.HTTPError, requests.exceptions.Timeout) as retry_exc:
        _log_http_error(api_url, retry_exc)
        return None
    except requests.exceptions.RequestException as retry_exc:
        logger.error("Request failed for Datajud API (%s): %s", api_url, retry_exc)
        return None
    except ValueError as retry_exc:
        logger.error(
            "Failed to decode JSON response from Datajud API (%s): %s",
            api_url, retry_exc,
        )
        return None


def _log_http_error(api_url: str, exc: BaseException) -> None:
    """Log uniforme para HTTPError/Timeout — comportamento da versao
    anterior preservado para mensagens de erro identicas."""
    if isinstance(exc, requests.exceptions.Timeout):
        logger.error("Timeout calling Datajud API (%s): %s", api_url, exc)
        return
    logger.error("HTTP Error calling Datajud API (%s): %s", api_url, exc)
    response = getattr(exc, "response", None)
    if response is not None:
        logger.error("Response status: %s", response.status_code)
        try:
            logger.error("Response content: %s", response.text[:1000])
        except Exception:
            logger.error("Could not retrieve error response content.")
    else:
        logger.error("No response object available in HTTPError.")
