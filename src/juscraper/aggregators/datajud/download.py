"""
Functions for downloading specific data from the Datajud API.
"""
import logging
from typing import Any, Dict, List, Optional, Union

import requests

from ...utils.cnj import clean_cnj

logger = logging.getLogger(__name__)


def build_listar_processos_payload(
    *,
    numero_processo: Optional[Union[str, List[str]]] = None,
    ano_ajuizamento: Optional[int] = None,
    classe: Optional[str] = None,
    assuntos: Optional[List[str]] = None,
    mostrar_movs: bool = False,
    tamanho_pagina: int = 1000,
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

    try:
        response = session.post(api_url, json=query_payload, headers=headers, timeout=timeout)
        if verbose:
            logger.debug("Response Status Code: %s", response.status_code)
            # Optionally log more details, but be mindful of verbosity and sensitive data
            # logger.debug(f"Response Headers: {response.headers}")
            # logger.debug(f"Response Content (first 500 chars): {response.text[:500]}")

        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
        data: Dict[str, Any] = response.json()
        return data

    except requests.exceptions.HTTPError as e:
        logger.error("HTTP Error calling Datajud API (%s): %s", api_url, e)
        if e.response is not None:
            logger.error("Response status: %s", e.response.status_code)
            try:
                logger.error("Response content: %s", e.response.text[:1000])
            except Exception:
                logger.error("Could not retrieve error response content.")
        else:
            logger.error("No response object available in HTTPError.")
        return None
    except requests.exceptions.Timeout:
        logger.error("Timeout calling Datajud API (%s) after %d seconds.", api_url, timeout)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Request failed for Datajud API (%s): %s", api_url, e)
        return None
    except ValueError as e:  # Includes JSONDecodeError if response is not valid JSON
        logger.error("Failed to decode JSON response from Datajud API (%s): %s", api_url, e)
        # Try to log part of the response text if available and decoding failed
        response_text_snippet = 'N/A'
        if 'response' in locals() and hasattr(response, 'text'):
            response_text_snippet = response.text[:500]
        logger.error("Response text (first 500 chars): %s", response_text_snippet)
        return None
    except Exception as e:
        logger.error("An unexpected error occurred calling Datajud API (%s): %s", api_url, e)
        return None
