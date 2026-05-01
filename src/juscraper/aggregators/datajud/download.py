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

# Tipo composto aceito por ``ano_ajuizamento``: int unico, range
# ``(inicio, fim)`` inclusivo, ou lista discreta de anos. Mantido aqui pra
# reuso entre listar_processos / contar_processos / schemas.
AnoAjuizamento = Union[int, "tuple[int, int]", List[int]]


def _build_ano_ajuizamento_clause(
    ano_ajuizamento: Optional[AnoAjuizamento],
) -> Optional[Dict[str, Any]]:
    """Constroi a clausula ``must`` para ``dataAjuizamento`` aceitando 3 formas
    de input. Retorna ``None`` quando ``ano_ajuizamento`` e None/vazio.

    Cada ano vira um par ``range`` (ISO + compacto) OR-ed via ``should`` —
    historico do datajud tem documentos com ``dataAjuizamento`` nos dois
    formatos, entao manter os dois e necessario pra cobertura.
    """
    if ano_ajuizamento is None:
        return None

    # Normaliza para uma lista de anos discretos.
    if isinstance(ano_ajuizamento, int):
        anos: List[int] = [ano_ajuizamento]
    elif isinstance(ano_ajuizamento, tuple):
        if len(ano_ajuizamento) != 2:
            raise ValueError(
                "ano_ajuizamento como tuple deve ser (inicio, fim) com 2 elementos."
            )
        lo, hi = sorted(ano_ajuizamento)
        anos = list(range(lo, hi + 1))
    else:  # list
        anos = list(ano_ajuizamento)

    if not anos:
        return None

    shoulds: List[Dict[str, Any]] = []
    for ano in anos:
        shoulds.append({
            "range": {
                "dataAjuizamento": {
                    "gte": f"{ano}-01-01",
                    "lte": f"{ano}-12-31",
                }
            }
        })
        shoulds.append({
            "range": {
                "dataAjuizamento": {
                    "gte": f"{ano}0101000000",
                    "lte": f"{ano}1231235959",
                }
            }
        })

    return {"bool": {"should": shoulds, "minimum_should_match": 1}}


def _build_classe_clause(
    classe: Optional[Union[str, List[str]]],
) -> Optional[Dict[str, Any]]:
    """``str`` -> ``match`` (1 codigo). ``list`` -> ``terms`` (varios codigos
    OR-ed). ``None``/vazio -> sem clausula."""
    if classe is None:
        return None
    if isinstance(classe, str):
        if not classe:
            return None
        return {"match": {"classe.codigo": classe}}
    codes = [str(c) for c in classe if str(c).strip()]
    if not codes:
        return None
    if len(codes) == 1:
        return {"match": {"classe.codigo": codes[0]}}
    return {"terms": {"classe.codigo": codes}}


def build_listar_processos_payload(
    *,
    numero_processo: Optional[Union[str, List[str]]] = None,
    ano_ajuizamento: Optional[AnoAjuizamento] = None,
    classe: Optional[Union[str, List[str]]] = None,
    assuntos: Optional[List[str]] = None,
    mostrar_movs: bool = False,
    tamanho_pagina: int = 5000,
    search_after: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Construir o body Elasticsearch para ``DatajudScraper.listar_processos``.

    Reune ``must_conditions`` (numero_processo / ano_ajuizamento / classe /
    assuntos), aplica o sort por ``id.keyword`` exigido pelo ``search_after``
    e controla o ``_source`` para incluir ou excluir movimentacoes/movimentos.
    A ordem das chaves e a logica condicional sao consumidas tal qual pelos
    contratos offline em ``tests/datajud/test_listar_processos_*_contract.py``
    via ``json_params_matcher`` — qualquer alteracao tem que ser refletida
    nos samples.

    ``ano_ajuizamento`` aceita ``int`` (ano unico, mantido por retro-compat),
    ``tuple[int, int]`` (range inclusivo) ou ``list[int]`` (anos discretos).
    ``classe`` aceita ``str`` (codigo unico) ou ``list[str]`` (varios codigos
    OR-ed via ``terms`` no ES).
    """
    must_conditions: List[Dict[str, Any]] = []
    if numero_processo:
        if isinstance(numero_processo, str):
            nproc = [numero_processo]
        else:
            nproc = list(numero_processo)
        nproc = [clean_cnj(n) for n in nproc]
        must_conditions.append({"terms": {"numeroProcesso": nproc}})

    ano_clause = _build_ano_ajuizamento_clause(ano_ajuizamento)
    if ano_clause is not None:
        must_conditions.append(ano_clause)

    classe_clause = _build_classe_clause(classe)
    if classe_clause is not None:
        must_conditions.append(classe_clause)

    if assuntos:
        must_conditions.append({"terms": {"assuntos.codigo": assuntos}})

    if must_conditions:
        query_values: Dict[str, Any] = {"bool": {"must": must_conditions}}
    else:
        query_values = {"match_all": {}}

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


def build_contar_processos_payload(
    *,
    numero_processo: Optional[Union[str, List[str]]] = None,
    ano_ajuizamento: Optional[AnoAjuizamento] = None,
    classe: Optional[Union[str, List[str]]] = None,
    assuntos: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Body Elasticsearch para ``DatajudScraper.contar_processos``.

    Reutiliza o mesmo conjunto de filtros de
    :func:`build_listar_processos_payload`, mas com ``size=0`` e
    ``track_total_hits=True`` — não baixa documento nenhum, apenas o
    ``hits.total`` (``value`` + ``relation``). Sem ``sort`` nem
    ``_source`` (não há paginação).

    ``ano_ajuizamento`` aceita ``int``, ``tuple[int, int]`` (range
    inclusivo) ou ``list[int]`` (anos discretos). ``classe`` aceita
    ``str`` ou ``list[str]``.
    """
    must_conditions: List[Dict[str, Any]] = []
    if numero_processo:
        if isinstance(numero_processo, str):
            nproc = [numero_processo]
        else:
            nproc = list(numero_processo)
        nproc = [clean_cnj(n) for n in nproc]
        must_conditions.append({"terms": {"numeroProcesso": nproc}})

    ano_clause = _build_ano_ajuizamento_clause(ano_ajuizamento)
    if ano_clause is not None:
        must_conditions.append(ano_clause)

    classe_clause = _build_classe_clause(classe)
    if classe_clause is not None:
        must_conditions.append(classe_clause)

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
