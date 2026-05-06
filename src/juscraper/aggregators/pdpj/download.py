"""Funcoes de download para o agregador PDPJ.

A API ``api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1``
e um conjunto de endpoints REST GET autenticados via JWT
(``Authorization: Bearer <token>``). Cada chamada devolve JSON estruturado
ou, no caso de ``/documentos/{id}/texto``, ``text/plain`` em UTF-8.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Base URL completa da API DATALAKE - API Processos.
BASE_URL = "https://api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Tempo padrao de timeout (segundos). Endpoints de detalhe podem demorar
# mais do que listagens — o caller pode sobrescrever.
DEFAULT_TIMEOUT = 30.0


def _request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = 5,
    backoff_factor: float = 1.0,
) -> requests.Response | None:
    """GET/HEAD com retry exponencial em ``429``/``503``/``Timeout``.

    Outros erros sobem direto via ``raise_for_status`` para o caller.
    Retorna ``None`` so quando esgotar as tentativas.
    """
    attempt = 0
    wait = backoff_factor
    while attempt <= max_retries:
        try:
            response = session.request(
                method, url, headers=headers, params=params, timeout=timeout
            )
            if response.status_code in (429, 503):
                logger.warning(
                    "[%s] %s para %s. Tentativa %d/%d. Aguardando %ss...",
                    response.status_code, method, url, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                attempt += 1
                wait = min(wait * 2, 32)
                continue
            response.raise_for_status()
            return response
        except requests.Timeout:
            logger.warning(
                "Timeout em %s %s (tentativa %d/%d).",
                method, url, attempt + 1, max_retries
            )
            time.sleep(wait)
            attempt += 1
            wait = min(wait * 2, 32)
        except requests.HTTPError as exc:
            # 4xx/5xx que nao sao 429/503 — surge para o caller decidir.
            logger.error("HTTP %s em %s %s: %s", exc.response.status_code, method, url, exc)
            raise
        except requests.RequestException as exc:
            logger.error("Erro de requisicao em %s %s: %s", method, url, exc)
            return None
    logger.error("Falha apos %d tentativas em %s %s.", max_retries, method, url)
    return None


def fetch_processo_existe(
    session: requests.Session,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> bool | None:
    """Indica se o processo existe na base do Data Lake (endpoint ``/existe``)."""
    url = f"{base_url}/processos/{numero_processo}/existe"
    response = _request_with_retry(session, "GET", url)
    if response is None:
        return None
    body = response.text.strip().lower()
    if body in ("true", "false"):
        return body == "true"
    try:
        return bool(response.json())
    except ValueError:
        logger.warning("Resposta inesperada de /existe para %s: %s", numero_processo, body[:80])
        return None


def fetch_processo_detalhes(
    session: requests.Session,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> list[dict[str, Any]]:
    """Recupera os detalhes do processo. A API responde com **lista** de tramitacoes."""
    url = f"{base_url}/processos/{numero_processo}"
    response = _request_with_retry(session, "GET", url)
    if response is None:
        return []
    data = response.json()
    if isinstance(data, dict):
        # Defensivo: alguns ambientes da API podem responder com um unico dict.
        return [data]
    if isinstance(data, list):
        return data
    logger.warning(
        "Resposta inesperada de /processos/%s: tipo %s",
        numero_processo, type(data).__name__,
    )
    return []


def fetch_processo_documentos(
    session: requests.Session,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any] | None:
    """Recupera a lista de documentos do processo."""
    url = f"{base_url}/processos/{numero_processo}/documentos"
    response = _request_with_retry(session, "GET", url)
    if response is None:
        return None
    data = response.json()
    if isinstance(data, dict):
        return data
    logger.warning(
        "Resposta inesperada de /documentos para %s: tipo %s",
        numero_processo, type(data).__name__,
    )
    return None


def fetch_processo_movimentos(
    session: requests.Session,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any] | None:
    """Recupera a lista de movimentos do processo."""
    url = f"{base_url}/processos/{numero_processo}/movimentos"
    response = _request_with_retry(session, "GET", url)
    if response is None:
        return None
    data = response.json()
    if isinstance(data, dict):
        return data
    return None


def fetch_processo_partes(
    session: requests.Session,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any] | None:
    """Recupera a lista de partes do processo."""
    url = f"{base_url}/processos/{numero_processo}/partes"
    response = _request_with_retry(session, "GET", url)
    if response is None:
        return None
    data = response.json()
    if isinstance(data, dict):
        return data
    return None


def fetch_documento_texto(
    session: requests.Session,
    numero_processo: str,
    id_documento: str,
    *,
    base_url: str = BASE_URL,
) -> str | None:
    """Recupera o texto bruto de um documento (UTF-8)."""
    url = f"{base_url}/processos/{numero_processo}/documentos/{id_documento}/texto"
    response = _request_with_retry(session, "GET", url, timeout=DEFAULT_TIMEOUT * 2)
    if response is None:
        return None
    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning(
            "Decodificacao UTF-8 falhou para doc %s do processo %s. Usando response.text.",
            id_documento, numero_processo,
        )
        return response.text


def fetch_documento_binario(
    session: requests.Session,
    numero_processo: str,
    id_documento: str,
    *,
    base_url: str = BASE_URL,
) -> bytes | None:
    """Recupera o binario do documento (HTML, PDF, imagem etc)."""
    url = f"{base_url}/processos/{numero_processo}/documentos/{id_documento}/binario"
    response = _request_with_retry(session, "GET", url, timeout=DEFAULT_TIMEOUT * 2)
    if response is None:
        return None
    return response.content


def fetch_documento_binario_url(
    session: requests.Session,
    numero_processo: str,
    id_documento: str,
    *,
    base_url: str = BASE_URL,
) -> str | None:
    """Retorna uma URL temporaria com TTL para o binario do documento."""
    url = f"{base_url}/processos/{numero_processo}/documentos/{id_documento}/binario-url"
    response = _request_with_retry(session, "GET", url)
    if response is None:
        return None
    return response.text.strip().strip('"')


def fetch_pesquisa(
    session: requests.Session,
    params: dict[str, Any],
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any] | None:
    """Pesquisa profunda em ``/processos`` (paginacao via ``searchAfter``)."""
    url = f"{base_url}/processos"
    response = _request_with_retry(session, "GET", url, params=params)
    if response is None:
        return None
    data = response.json()
    if isinstance(data, dict):
        return data
    return None


def fetch_contar(
    session: requests.Session,
    params: dict[str, Any],
    *,
    base_url: str = BASE_URL,
) -> int | None:
    """Total de processos que casam com ``params`` (``/processos:contar``)."""
    url = f"{base_url}/processos:contar"
    response = _request_with_retry(session, "GET", url, params=params)
    if response is None:
        return None
    body = response.text.strip()
    try:
        return int(body)
    except (TypeError, ValueError):
        try:
            data = response.json()
        except ValueError:
            logger.warning("Resposta inesperada de /processos:contar: %s", body[:120])
            return None
        if isinstance(data, int):
            return data
        if isinstance(data, dict):
            for key in ("total", "count", "valor"):
                if isinstance(data.get(key), int):
                    return data[key]
        return None
