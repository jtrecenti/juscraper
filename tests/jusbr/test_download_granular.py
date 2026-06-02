"""Testes granulares para ``juscraper.aggregators.jusbr.download``.

Cobre o contrato pos-#204: cada ``fetch_*`` recebe um ``request_fn``
(callable equivalente a ``HTTPScraper._request_with_retry``) e devolve
``None`` quando o request_fn levanta ``RetryExhaustedError`` ou
``requests.RequestException``. O happy path tambem e validado para
evitar regressao no parse minimo (`response.json()` /
`response.content.decode("utf-8")`).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from juscraper.aggregators.jusbr.download import (
    fetch_document_binary,
    fetch_document_text,
    fetch_process_details,
    fetch_process_list,
)
from juscraper.core.exceptions import RetryExhaustedError

BASE_API_URL_V2 = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"
BASE_API_URL_V1_DOCS = (
    "https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos/"
)
CNJ = "12345678901234567890"
DOC_ID = "abc-uuid"


def _retry_exhausted_request_fn():
    """``request_fn`` que sempre estoura o retry."""
    return MagicMock(side_effect=RetryExhaustedError(503, 3))


def _request_exception_request_fn(exc: type[requests.RequestException]):
    """``request_fn`` que levanta ``exc`` na primeira chamada."""
    return MagicMock(side_effect=exc("boom"))


# ---------------------------------------------------------------------------
# fetch_process_list
# ---------------------------------------------------------------------------


def test_fetch_process_list_retry_exhausted_returns_none():
    request_fn = _retry_exhausted_request_fn()
    result = fetch_process_list(request_fn, CNJ, BASE_API_URL_V2)
    assert result is None
    request_fn.assert_called_once()


def test_fetch_process_list_timeout_returns_none():
    request_fn = _request_exception_request_fn(requests.Timeout)
    assert fetch_process_list(request_fn, CNJ, BASE_API_URL_V2) is None


def test_fetch_process_list_happy_path_returns_json():
    response = MagicMock(spec=requests.Response)
    response.json.return_value = {"content": [{"numeroProcesso": CNJ}]}
    request_fn = MagicMock(return_value=response)

    result = fetch_process_list(request_fn, CNJ, BASE_API_URL_V2)

    assert result == {"content": [{"numeroProcesso": CNJ}]}
    method, url = request_fn.call_args.args
    assert method == "GET"
    assert url.endswith(f"?numeroProcesso={CNJ}")


# ---------------------------------------------------------------------------
# fetch_process_details
# ---------------------------------------------------------------------------


def test_fetch_process_details_retry_exhausted_returns_none():
    request_fn = _retry_exhausted_request_fn()
    assert fetch_process_details(request_fn, CNJ, BASE_API_URL_V2) is None


def test_fetch_process_details_request_exception_returns_none():
    request_fn = _request_exception_request_fn(requests.ConnectionError)
    assert fetch_process_details(request_fn, CNJ, BASE_API_URL_V2) is None


def test_fetch_process_details_happy_path_returns_json():
    response = MagicMock(spec=requests.Response)
    response.json.return_value = {"numeroProcesso": CNJ, "detalhes": {}}
    request_fn = MagicMock(return_value=response)

    result = fetch_process_details(request_fn, CNJ, BASE_API_URL_V2)

    assert result == {"numeroProcesso": CNJ, "detalhes": {}}


# ---------------------------------------------------------------------------
# fetch_document_text
# ---------------------------------------------------------------------------


def test_fetch_document_text_retry_exhausted_returns_none():
    request_fn = _retry_exhausted_request_fn()
    result = fetch_document_text(
        request_fn, CNJ, DOC_ID, BASE_API_URL_V1_DOCS, authorization="Bearer token"
    )
    assert result is None


def test_fetch_document_text_timeout_returns_none():
    request_fn = _request_exception_request_fn(requests.Timeout)
    assert (
        fetch_document_text(
            request_fn, CNJ, DOC_ID, BASE_API_URL_V1_DOCS, authorization=""
        )
        is None
    )


def test_fetch_document_text_happy_path_decodes_utf8():
    response = MagicMock(spec=requests.Response)
    response.content = "conteúdo do documento".encode("utf-8")
    request_fn = MagicMock(return_value=response)

    result = fetch_document_text(
        request_fn, CNJ, DOC_ID, BASE_API_URL_V1_DOCS, authorization="Bearer token"
    )

    assert result == "conteúdo do documento"
    # ``authorization`` deve viajar nos headers explicitos do request.
    headers = request_fn.call_args.kwargs["headers"]
    assert headers["authorization"] == "Bearer token"


def test_fetch_document_text_falls_back_to_response_text_on_unicode_error():
    response = MagicMock(spec=requests.Response)
    response.content = MagicMock()
    response.content.decode.side_effect = UnicodeDecodeError(
        "utf-8", b"\xff", 0, 1, "bad"
    )
    response.encoding = "latin-1"
    response.text = "fallback content"
    request_fn = MagicMock(return_value=response)

    result = fetch_document_text(
        request_fn, CNJ, DOC_ID, BASE_API_URL_V1_DOCS, authorization=""
    )

    assert result == "fallback content"


# ---------------------------------------------------------------------------
# fetch_document_binary
# ---------------------------------------------------------------------------


def test_fetch_document_binary_retry_exhausted_returns_none():
    request_fn = _retry_exhausted_request_fn()
    assert (
        fetch_document_binary(request_fn, CNJ, DOC_ID, BASE_API_URL_V2) is None
    )


def test_fetch_document_binary_request_exception_returns_none():
    request_fn = _request_exception_request_fn(requests.ConnectionError)
    assert (
        fetch_document_binary(request_fn, CNJ, DOC_ID, BASE_API_URL_V2) is None
    )


def test_fetch_document_binary_happy_path_returns_bytes():
    response = MagicMock(spec=requests.Response)
    response.content = b"PDF-binary-payload"
    request_fn = MagicMock(return_value=response)

    result = fetch_document_binary(request_fn, CNJ, DOC_ID, BASE_API_URL_V2)

    assert result == b"PDF-binary-payload"


# ---------------------------------------------------------------------------
# Smoke: schema do request_fn esperado por todas as funcoes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fetch_fn, extra_args, extra_kwargs",
    [
        (fetch_process_list, (CNJ, BASE_API_URL_V2), {}),
        (fetch_process_details, (CNJ, BASE_API_URL_V2), {}),
        (fetch_document_text, (CNJ, DOC_ID, BASE_API_URL_V1_DOCS), {"authorization": ""}),
        (fetch_document_binary, (CNJ, DOC_ID, BASE_API_URL_V2), {}),
    ],
)
def test_request_fn_is_called_with_get_and_positional_url(
    fetch_fn, extra_args, extra_kwargs
):
    """Todas as funcoes invocam request_fn como ``("GET", url, **kwargs)``."""
    response = MagicMock(spec=requests.Response)
    response.json.return_value = {}
    response.content = b""
    request_fn = MagicMock(return_value=response)

    fetch_fn(request_fn, *extra_args, **extra_kwargs)

    method, url = request_fn.call_args.args
    assert method == "GET"
    assert url.startswith("http")
