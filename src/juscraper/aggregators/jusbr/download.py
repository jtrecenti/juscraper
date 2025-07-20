"""
Funções de download específicas para JUSBR
"""

import logging
import time
from typing import Optional, Dict, Any
import requests
from ...utils.cnj import clean_cnj

logger = logging.getLogger(__name__)

def request_with_retry(session, url, *, headers=None, timeout=15, max_retries=5, backoff_factor=1.0, **kwargs):
    """
    Faz uma requisição GET com retry exponencial para status 429 (Too Many Requests).
    """
    attempt = 0
    wait = backoff_factor
    while attempt <= max_retries:
        try:
            response = session.get(url, headers=headers, timeout=timeout, **kwargs)
            if response.status_code == 429:
                logger.warning(f"[429] Too Many Requests para {url}. Tentativa {attempt+1}/{max_retries}. Aguardando {wait}s...")
                time.sleep(wait)
                attempt += 1
                wait = min(wait * 2, 32)  # Limite de 32 segundos
                continue
            response.raise_for_status()
            return response
        except requests.Timeout:
            logger.error(f"Timeout ao acessar {url} (tentativa {attempt+1}/{max_retries})")
            time.sleep(wait)
            attempt += 1
            wait = min(wait * 2, 32)
        except requests.RequestException as e:
            logger.error(f"Erro de requisição em {url}: {e} (tentativa {attempt+1}/{max_retries})")
            # Só faz retry se for 429, outros erros retornam direto
            break
    logger.error(f"Falha após {max_retries} tentativas para {url}")
    return None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
)

def fetch_process_list(
    session: requests.Session,
    cnj_cleaned: str,
    base_api_url: str
) -> Optional[Dict[str, Any]]:
    """
    Fetches the initial list of processes matching a CNJ.
    Corresponds to the first API call in the original cpopg.
    """
    url = f"{base_api_url}?numeroProcesso={cnj_cleaned}"
    logger.debug("Fetching process list from: %s", url)
    try:
        response = request_with_retry(session, url, timeout=15)
        if response is None:
            return None
        return response.json()
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
    session: requests.Session,
    numero_processo_oficial: str,
    base_api_url: str
) -> Optional[Dict[str, Any]]:
    """
    Fetches detailed information for a specific official process number.
    Corresponds to the second API call in the original cpopg.
    """
    url = f"{base_api_url}{numero_processo_oficial}"
    logger.debug("Fetching process details from: %s", url)
    try:
        response = request_with_retry(session, url, timeout=15)
        if response is None:
            return None
        return response.json()
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
    session: requests.Session,
    numero_processo: str,
    id_documento: str,
    base_api_url_docs: str
) -> Optional[str]:
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

    # Headers explícitos (garante todos)
    request_headers = {
        'accept': '*/*',
        'authorization': session.headers.get('authorization', ''),
        'user-agent': USER_AGENT,
        'referer': 'https://portaldeservicos.pdpj.jus.br/consulta',
    }

    logger.debug("[JUSBR DEBUG] Baixando documento: URL=%s", doc_url)
    logger.debug("[JUSBR DEBUG] Headers: %s", request_headers)

    try:
        response = request_with_retry(session, doc_url, headers=request_headers, timeout=30)
        if response is None:
            return None
        try:
            return response.content.decode('utf-8')
        except UnicodeDecodeError:
            logger.warning(
                "UTF-8 decoding failed for document %s of process %s."
                "Falling back to response.text (detected encoding: %s)",
                id_documento, numero_processo, response.encoding
            )
            return response.text  # Fallback to requests' auto-detected encoding
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
    session: requests.Session,
    numero_processo: str,
    id_documento: str,
    base_api_url_docs: str
) -> Optional[str]:
    numero_processo_param = numero_processo  # original, pode estar com máscara
    doc_url = (
        f"{base_api_url_docs.rstrip('/')}/{numero_processo_param}/documentos/{id_documento}/binario"
    )
    logger.debug("Fetching document binary from: %s", doc_url)
    try:
        response = request_with_retry(session, doc_url, timeout=15)
        if response is None:
            return None
        return response.content
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