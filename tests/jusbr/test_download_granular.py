"""Testes granulares para ``juscraper.aggregators.jusbr.download``.

Cada ``fetch_*`` recebe um ``request_fn`` (callable equivalente a
``HTTPScraper._request_with_retry``) e propaga o erro dele: quem decide entre
linha de falha e interrupção do lote é o client. A única exceção é o 404 da
listagem, que vira lista vazia. O happy path também é validado para evitar
regressão no parse mínimo (`response.json()` / `response.content.decode("utf-8")`).
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
from juscraper.core.exceptions import InvalidJSONResponseError, RetryExhaustedError

BASE_API_URL_V2 = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"
BASE_API_URL_V1_DOCS = (
    "https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos/"
)
CNJ = "12345678901234567890"
DOC_ID = "abc-uuid"


def _http_error(status: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(f"{status}", response=resp)


def _json_response(payload) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.json.return_value = payload
    response.status_code = 200
    response.headers = {"Content-Type": "application/json"}
    response.text = str(payload)
    response.content = b""
    return response


_ERROS_PROPAGADOS = [
    RetryExhaustedError(503, 3),
    requests.Timeout("lento"),
    requests.ConnectionError("fora do ar"),
    _http_error(401),
    _http_error(403),
    _http_error(500),
]

_FETCHES = [
    pytest.param(fetch_process_details, (CNJ, BASE_API_URL_V2), {}, id="details"),
    pytest.param(
        fetch_document_text, (CNJ, DOC_ID, BASE_API_URL_V1_DOCS), {"authorization": ""}, id="texto"
    ),
    pytest.param(fetch_document_binary, (CNJ, DOC_ID, BASE_API_URL_V2), {}, id="binario"),
]


# ---------------------------------------------------------------------------
# Nenhum fetch_* absorve erro: o client decide entre linha de falha e 401
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("erro", _ERROS_PROPAGADOS, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("fetch_fn, extra_args, extra_kwargs", [
    pytest.param(fetch_process_list, (CNJ, BASE_API_URL_V2), {}, id="lista"), *_FETCHES,
])
def test_fetch_propaga_erro_do_request_fn(fetch_fn, extra_args, extra_kwargs, erro):
    request_fn = MagicMock(side_effect=erro)
    with pytest.raises(type(erro)) as capturado:
        fetch_fn(request_fn, *extra_args, **extra_kwargs)
    assert capturado.value is erro
    request_fn.assert_called_once()


@pytest.mark.parametrize("fetch_fn, extra_args, extra_kwargs", _FETCHES)
def test_404_fora_da_listagem_propaga(fetch_fn, extra_args, extra_kwargs):
    """Só a listagem documenta o 404 como CNJ inexistente."""
    request_fn = MagicMock(side_effect=_http_error(404))
    with pytest.raises(requests.HTTPError):
        fetch_fn(request_fn, *extra_args, **extra_kwargs)


# ---------------------------------------------------------------------------
# fetch_process_list
# ---------------------------------------------------------------------------


def test_fetch_process_list_404_e_lista_vazia():
    request_fn = MagicMock(side_effect=_http_error(404))
    assert fetch_process_list(request_fn, CNJ, BASE_API_URL_V2) == {"content": []}


@pytest.mark.parametrize(
    "payload",
    [[{"numeroProcesso": CNJ}], {"content": {"numeroProcesso": CNJ}}, {"outra": []}, "texto"],
    ids=["lista", "content-objeto", "sem-content", "escalar"],
)
def test_fetch_process_list_forma_errada_levanta_json_invalido(payload):
    request_fn = MagicMock(return_value=_json_response(payload))
    with pytest.raises(InvalidJSONResponseError):
        fetch_process_list(request_fn, CNJ, BASE_API_URL_V2)


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


def test_fetch_process_details_happy_path_returns_json():
    response = MagicMock(spec=requests.Response)
    response.json.return_value = {"numeroProcesso": CNJ, "detalhes": {}}
    request_fn = MagicMock(return_value=response)

    result = fetch_process_details(request_fn, CNJ, BASE_API_URL_V2)

    assert result == {"numeroProcesso": CNJ, "detalhes": {}}


def test_fetch_process_details_aceita_lista_com_objeto():
    """Forma dos samples capturados: lista com o objeto de detalhes."""
    request_fn = MagicMock(return_value=_json_response([{"numeroProcesso": CNJ}]))
    assert fetch_process_details(request_fn, CNJ, BASE_API_URL_V2) == [{"numeroProcesso": CNJ}]


@pytest.mark.parametrize("payload", [[], ["texto"], "texto", 3], ids=["vazia", "lista-escalar", "str", "int"])
def test_fetch_process_details_forma_errada_levanta_json_invalido(payload):
    request_fn = MagicMock(return_value=_json_response(payload))
    with pytest.raises(InvalidJSONResponseError):
        fetch_process_details(request_fn, CNJ, BASE_API_URL_V2)


# ---------------------------------------------------------------------------
# fetch_document_text
# ---------------------------------------------------------------------------


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
    request_fn = MagicMock(return_value=_json_response({"content": []}))

    fetch_fn(request_fn, *extra_args, **extra_kwargs)

    method, url = request_fn.call_args.args
    assert method == "GET"
    assert url.startswith("http")


@pytest.mark.parametrize(
    "fetch_fn, extra_args, extra_kwargs, perfil",
    [
        (fetch_process_list, (CNJ, BASE_API_URL_V2), {}, "listagem"),
        (fetch_process_details, (CNJ, BASE_API_URL_V2), {}, "listagem"),
        (fetch_document_text, (CNJ, DOC_ID, BASE_API_URL_V1_DOCS), {"authorization": ""}, "documento"),
        (fetch_document_binary, (CNJ, DOC_ID, BASE_API_URL_V2), {}, "documento"),
    ],
)
def test_fetch_usa_perfil_sem_timeout_literal(fetch_fn, extra_args, extra_kwargs, perfil):
    """``timeout=`` na chamada venceria o perfil e anularia ``politica=``."""
    request_fn = MagicMock(return_value=_json_response({"content": []}))

    fetch_fn(request_fn, *extra_args, **extra_kwargs)

    assert request_fn.call_args.kwargs["perfil"] == perfil
    assert "timeout" not in request_fn.call_args.kwargs
