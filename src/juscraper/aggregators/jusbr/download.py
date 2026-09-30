"""Funções de download específicas para JUSBR.

Os ``fetch_*`` recebem um ``request_fn``, tipicamente o
``HTTPScraper._request_with_retry`` ligado do scraper, que aplica o perfil de
requisição ("listagem" ou "documento") declarado em
:attr:`juscraper.aggregators.jusbr.client.JusbrScraper.perfis_http`.

Nenhum ``fetch_*`` absorve erro: ``HTTPError``, ``RetryExhaustedError``,
``Timeout``, ``ConnectionError`` e ``InvalidJSONResponseError`` sobem ao
:mod:`client`, que decide entre interromper o lote (401) e registrar a linha de
falha com o motivo. A única exceção é o 404 da listagem, que a API usa para
dizer que o CNJ não existe (ver :func:`fetch_process_list`).
"""

import logging
from collections.abc import Callable
from typing import Any

import requests

from ...core.exceptions import InvalidJSONResponseError
from ...utils.cnj import clean_cnj
from ...utils.logging_cfg import redact_headers

logger = logging.getLogger(__name__)


# Type alias: contrato mínimo do callable usado pelos fetch_*. Mesma assinatura
# de ``HTTPScraper._request_with_retry`` (method, url, **kwargs) -> Response.
RequestFn = Callable[..., requests.Response]


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
)

# A listagem responde 404 com JSON de erro para CNJ inexistente, nunca 200 com
# ``content`` vazio (``tests/fixtures/capture/README.md``). Nos detalhes e nos
# documentos, o 404 não está documentado como ausência e conta como falha.
_STATUS_CNJ_INEXISTENTE = 404


def _forma_invalida(response: requests.Response, url: str) -> InvalidJSONResponseError:
    """Erro para um corpo JSON válido na forma que o endpoint não usa.

    O ``request_fn`` é chamado com ``expect_json=True``, então o corpo já é
    JSON; o erro aqui é de forma, e sai com o mesmo motivo ``json_invalido``.
    """
    return InvalidJSONResponseError(
        url, response.status_code, 1, response.headers.get("Content-Type"), response.text[:200]
    )


def fetch_process_list(
    request_fn: RequestFn,
    cnj_cleaned: str,
    base_api_url: str
) -> dict[str, Any]:
    """Busca a lista de processos que casam com um CNJ.

    Returns:
        O objeto JSON da listagem. Para CNJ inexistente (404), ``{"content": []}``,
        que o :mod:`client` registra como "Nao encontrado na lista inicial".

    Raises:
        requests.HTTPError: Status 4xx diferente de 404.
        RetryExhaustedError, requests.Timeout, requests.ConnectionError: Ver
            ``HTTPScraper._request_with_retry``.
        InvalidJSONResponseError: Corpo que não é JSON, ou objeto sem a lista
            ``content``.
    """
    url = f"{base_api_url}?numeroProcesso={cnj_cleaned}"
    logger.debug("Fetching process list from: %s", url)
    try:
        response = request_fn("GET", url, perfil="listagem", expect_json=True)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == _STATUS_CNJ_INEXISTENTE:
            logger.info("CNJ %s inexistente na listagem (HTTP 404).", cnj_cleaned)
            return {"content": []}
        raise
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("content"), list):
        raise _forma_invalida(response, url)
    return data


def fetch_process_details(
    request_fn: RequestFn,
    numero_processo_oficial: str,
    base_api_url: str
) -> dict[str, Any] | list[dict[str, Any]]:
    """Busca os detalhes de um processo pelo número oficial.

    A API devolve uma lista com o objeto de detalhes (forma dos samples
    capturados); um objeto solto também é aceito, e o parser trata os dois.

    Raises:
        requests.HTTPError: Status 4xx, inclusive o 404.
        RetryExhaustedError, requests.Timeout, requests.ConnectionError: Ver
            ``HTTPScraper._request_with_retry``.
        InvalidJSONResponseError: Corpo que não é JSON, ou que não é objeto nem
            lista cujo primeiro item é objeto.
    """
    url = f"{base_api_url}{numero_processo_oficial}"
    logger.debug("Fetching process details from: %s", url)
    response = request_fn("GET", url, perfil="listagem", expect_json=True)
    data = response.json()
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data
    raise _forma_invalida(response, url)


def fetch_document_text(
    request_fn: RequestFn,
    numero_processo: str,
    id_documento: str,
    base_api_url_docs: str,
    *,
    authorization: str = "",
) -> str:
    """Baixa o texto bruto de um documento.

    Raises:
        requests.HTTPError, RetryExhaustedError, requests.Timeout,
            requests.ConnectionError: Ver ``HTTPScraper._request_with_retry``.
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
    logger.debug("[JUSBR DEBUG] Headers: %s", redact_headers(request_headers))

    response = request_fn("GET", doc_url, headers=request_headers, perfil="documento")
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


def fetch_document_binary(
    request_fn: RequestFn,
    numero_processo: str,
    id_documento: str,
    base_api_url_docs: str
) -> bytes:
    """Baixa o binário de um documento.

    Raises:
        requests.HTTPError, RetryExhaustedError, requests.Timeout,
            requests.ConnectionError: Ver ``HTTPScraper._request_with_retry``.
    """
    numero_processo_param = numero_processo  # original, pode estar com máscara
    doc_url = (
        f"{base_api_url_docs.rstrip('/')}/{numero_processo_param}/documentos/{id_documento}/binario"
    )
    logger.debug("Fetching document binary from: %s", doc_url)
    response = request_fn("GET", doc_url, perfil="documento")
    content: bytes = response.content
    return content
