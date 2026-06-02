"""Funções de download específicas para JUSBR.

Antes da migração para :class:`juscraper.core.http.HTTPScraper` (issue #204),
este módulo tinha seu próprio ``request_with_retry`` duplicando a lógica de
backoff. Agora os ``fetch_*`` recebem um ``request_fn`` — tipicamente o
``HTTPScraper._request_with_retry`` ligado do scraper — e centralizam o retry
na infra compartilhada (#201). Os erros são absorvidos aqui e devolvidos como
``None`` para preservar o contrato dos callers em :mod:`client`.
"""

import logging
from collections.abc import Callable
from typing import Any

import requests

from ...core.exceptions import RetryExhaustedError
from ...utils.cnj import clean_cnj

logger = logging.getLogger(__name__)


# Type alias: contrato mínimo do callable usado pelos fetch_*. Mesma assinatura
# de ``HTTPScraper._request_with_retry`` (method, url, **kwargs) -> Response.
RequestFn = Callable[..., requests.Response]


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
)


def fetch_process_list(
    request_fn: RequestFn,
    cnj_cleaned: str,
    base_api_url: str
) -> dict[str, Any] | None:
    """
    Fetches the initial list of processes matching a CNJ.
    Corresponds to the first API call in the original cpopg.
    """
    url = f"{base_api_url}?numeroProcesso={cnj_cleaned}"
    logger.debug("Fetching process list from: %s", url)
    try:
        response = request_fn("GET", url, timeout=15)
        data: dict[str, Any] = response.json()
        return data
    except RetryExhaustedError as exc:
        logger.error(
            "Retry exausto ao buscar lista de processos para %s em %s: %s",
            cnj_cleaned, url, exc,
        )
        return None
    except requests.Timeout:
        logger.error(
            "Timeout ao buscar lista de processos para %s em %s",
            cnj_cleaned, url
        )
        return None
    except requests.RequestException as e:
        logger.error(
            "Erro ao buscar lista de processos para %s em %s: %s",
            cnj_cleaned, url, e
        )
        return None
    except ValueError as e:  # JSONDecodeError
        logger.error(
            "Erro ao decodificar JSON da lista de processos para %s em %s: %s",
            cnj_cleaned, url, e
        )
        return None


def fetch_process_details(
    request_fn: RequestFn,
    numero_processo_oficial: str,
    base_api_url: str
) -> dict[str, Any] | None:
    """
    Fetches detailed information for a specific official process number.
    Corresponds to the second API call in the original cpopg.
    """
    url = f"{base_api_url}{numero_processo_oficial}"
    logger.debug("Fetching process details from: %s", url)
    try:
        response = request_fn("GET", url, timeout=15)
        data: dict[str, Any] = response.json()
        return data
    except RetryExhaustedError as exc:
        logger.error(
            "Retry exausto ao buscar detalhes do processo %s em %s: %s",
            numero_processo_oficial, url, exc,
        )
        return None
    except requests.Timeout:
        logger.error(
            "Timeout ao buscar detalhes do processo %s em %s",
            numero_processo_oficial, url
        )
        return None
    except requests.RequestException as e:
        logger.error(
            "Erro ao buscar detalhes do processo %s em %s: %s",
            numero_processo_oficial, url, e
        )
        return None
    except ValueError as e:  # JSONDecodeError
        logger.error(
            "Erro ao decodificar JSON dos detalhes do processo %s em %s: %s",
            numero_processo_oficial, url, e
        )
        return None


def fetch_document_text(
    request_fn: RequestFn,
    numero_processo: str,
    id_documento: str,
    base_api_url_docs: str,
    *,
    authorization: str = "",
) -> str | None:
    """
    Fetches the raw text of a specific document for a given process number.
    """
    # Recebe o CNJ limpo na URL, mas espera o CNJ original (com máscara) para a query string
    numero_processo_url = clean_cnj(numero_processo)
    numero_processo_param = numero_processo  # original, pode estar com máscara
    doc_url = (
        f"{base_api_url_docs.rstrip('/')}/{numero_processo_url}/documentos/{id_documento}/texto"
        f"?numeroProcesso={numero_processo_param}&idDocumento={id_documento}"
    )

    # Headers explícitos por requisição (override dos defaults da session).
    # Antes da migração, o caller lia ``session.headers['authorization']`` aqui;
    # agora o caller passa explicitamente em ``authorization`` para que o
    # request_fn (``_request_with_retry``) não precise ser ``self`` consciente.
    request_headers = {
        'accept': '*/*',
        'authorization': authorization,
        'user-agent': USER_AGENT,
        'referer': 'https://portaldeservicos.pdpj.jus.br/consulta',
    }

    logger.debug("[JUSBR DEBUG] Baixando documento: URL=%s", doc_url)
    logger.debug("[JUSBR DEBUG] Headers: %s", request_headers)

    response: requests.Response | None = None
    try:
        response = request_fn("GET", doc_url, headers=request_headers, timeout=30)
        try:
            content_str: str = response.content.decode('utf-8')
            return content_str
        except UnicodeDecodeError:
            logger.warning(
                "UTF-8 decoding failed for document %s of process %s."
                "Falling back to response.text (detected encoding: %s)",
                id_documento, numero_processo, response.encoding
            )
            fallback: str = response.text  # Fallback to requests' auto-detected encoding
            return fallback
    except RetryExhaustedError as exc:
        logger.error(
            "Retry exausto ao baixar documento %s do processo %s (URL: %s): %s",
            id_documento, numero_processo, doc_url, exc,
        )
    except requests.exceptions.HTTPError as e:
        logger.error(
            "HTTP Error fetching document %s for process %s (URL: %s): %s. Response: %s",
            id_documento, numero_processo, doc_url, e, response.text[:200] if response else "N/A"
        )
    except requests.exceptions.RequestException as e:
        logger.error(
            "Request Exception fetching document %s for process %s (URL: %s): %s",
            id_documento, numero_processo, doc_url, e
        )
    # Catching Exception as a last resort to avoid
    # crashing on unexpected errors during scraping.
    # All known exceptions are handled above;
    # this is to log and continue in production environments.
    except Exception as e:
        logger.error(
            "Unexpected error fetching document %s for process %s (URL: %s): %s",
            id_documento, numero_processo, doc_url, e
        )
    return None


def fetch_document_binary(
    request_fn: RequestFn,
    numero_processo: str,
    id_documento: str,
    base_api_url_docs: str
) -> bytes | None:
    """Fetch the binary payload of a document from the JusBR API."""
    numero_processo_param = numero_processo  # original, pode estar com máscara
    doc_url = (
        f"{base_api_url_docs.rstrip('/')}/{numero_processo_param}/documentos/{id_documento}/binario"
    )
    logger.debug("Fetching document binary from: %s", doc_url)
    try:
        response = request_fn("GET", doc_url, timeout=15)
        content: bytes = response.content
        return content
    except RetryExhaustedError as exc:
        logger.error(
            "Retry exausto ao baixar binário do documento %s para processo %s em %s: %s",
            id_documento, numero_processo, doc_url, exc,
        )
        return None
    except requests.Timeout:
        logger.error(
            "Timeout ao buscar binário do documento %s para processo %s em %s",
            id_documento, numero_processo, doc_url
        )
        return None
    except requests.RequestException as e:
        logger.error(
            "Erro ao buscar binário do documento %s para processo %s em %s: %s",
            id_documento, numero_processo, doc_url, e
        )
        return None
