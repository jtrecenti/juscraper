"""Testes de ``juscraper.core.failures.motivo_falha``: um caso por valor do vocabulário."""
from __future__ import annotations

import pytest
import requests

from juscraper.core.exceptions import InvalidJSONResponseError, RetryExhaustedError
from juscraper.core.failures import COLUNA_MOTIVO_FALHA, MOTIVOS_FALHA, motivo_falha


def _http_error(status: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(f"{status}", response=resp)


@pytest.mark.parametrize(
    ("exc", "esperado"),
    [
        (_http_error(404), "http_404"),
        (_http_error(403), "http_403"),
        (RetryExhaustedError(503, 3), "retry_esgotado_503"),
        (requests.ReadTimeout(), "timeout"),
        (requests.Timeout(), "timeout"),
        (requests.ConnectionError(), "conexao"),
        (InvalidJSONResponseError("https://example.test", 200, 3), "json_invalido"),
    ],
)
def test_motivo_falha_por_excecao(exc, esperado):
    assert motivo_falha(exc) == esperado


def test_connect_timeout_e_conexao_e_nao_timeout():
    """``ConnectTimeout`` herda de ``ConnectionError`` e de ``Timeout``; sai ``conexao``."""
    assert isinstance(requests.ConnectTimeout(), requests.Timeout)
    assert motivo_falha(requests.ConnectTimeout()) == "conexao"


@pytest.mark.parametrize(
    "exc",
    [
        requests.TooManyRedirects(),
        requests.exceptions.InvalidURL(),
        ValueError("parse"),
        requests.HTTPError("sem resposta"),
        RetryExhaustedError(None, 3),
    ],
)
def test_motivo_falha_fora_do_vocabulario_levanta_typeerror(exc):
    with pytest.raises(TypeError) as info:
        motivo_falha(exc)
    assert info.value.__cause__ is exc


def test_vocabulario_publicado():
    assert COLUNA_MOTIVO_FALHA == "motivo_falha"
    assert set(MOTIVOS_FALHA) == {"http_<status>", "retry_esgotado_<status>", "timeout", "conexao", "json_invalido"}
