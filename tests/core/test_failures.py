"""Testes de ``juscraper.core.failures``: o vocabulário do motivo, o aviso agregado e a nota do 401."""
from __future__ import annotations

import pytest
import requests

from juscraper.core.exceptions import (
    BloqueioAntiBotWarning,
    BotChallengeBlockedError,
    InvalidJSONResponseError,
    RetryExhaustedError,
    WafChallengeError,
)
from juscraper.core.failures import (
    COLUNA_MOTIVO_FALHA,
    EXCECOES_DE_FALHA_POR_LINHA,
    EXEMPLOS_NO_AVISO,
    MOTIVOS_FALHA,
    STATUS_CONSULTA_FALHA,
    STATUS_TOKEN_INVALIDO,
    anotar_falhas_anteriores,
    avisar_falhas,
    e_token_invalido,
    motivo_falha,
    resumir_falhas,
)


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
        (requests.JSONDecodeError("Expecting value", "<html>", 0), "json_invalido"),
        (BotChallengeBlockedError("TRF3", "https://example.test"), "bloqueio_anti_bot"),
        (WafChallengeError("TJPE", "https://example.test"), "bloqueio_anti_bot"),
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
    assert set(MOTIVOS_FALHA) == {
        "http_<status>", "retry_esgotado_<status>", "timeout", "conexao", "json_invalido", "nao_encontrado",
        "sem_acordao", "nao_pdf", "resposta_inesperada", "entrada_invalida", "bloqueio_anti_bot",
    }


# ---------------------------------------------------------------------------
# Aviso agregado, nota do 401 e classificação das exceções
# ---------------------------------------------------------------------------


def test_resumir_falhas_cita_tres_e_conta_o_resto():
    falhas = [f"item {i}: http_500" for i in range(5)]
    resumo = resumir_falhas(falhas, "consulta(s) de processo")
    assert resumo == (
        "5 consulta(s) de processo falharam. Falhas: item 0: http_500; item 1: http_500; "
        "item 2: http_500; e mais 2."
    )
    assert EXEMPLOS_NO_AVISO == 3


def test_resumir_falhas_sem_excedente_nao_diz_e_mais():
    assert "e mais" not in resumir_falhas(["a", "b", "c"], "download(s) de documento")


def test_avisar_falhas_emite_um_aviso_com_o_metodo():
    with pytest.warns(UserWarning, match=r"^Scraper\.metodo: 1 download\(s\) de documento falharam") as avisos:
        avisar_falhas(["doc 1: timeout"], "Scraper.metodo", "download(s) de documento")
    assert len(avisos) == 1
    assert avisos[0].category is UserWarning


def test_avisar_falhas_com_bloqueio_usa_categoria_propria_mesmo_fora_dos_exemplos():
    falhas = [f"doc {i}: timeout" for i in range(EXEMPLOS_NO_AVISO)] + ["doc 9: bloqueio_anti_bot"]
    with pytest.warns(BloqueioAntiBotWarning) as avisos:
        avisar_falhas(falhas, "Scraper.metodo", "download(s) de documento")
    assert len(avisos) == 1
    assert "bloqueio_anti_bot" not in str(avisos[0].message)


def test_avisar_falhas_sem_falha_nao_avisa(recwarn):
    avisar_falhas([], "Scraper.metodo", "download(s) de documento")
    assert len(recwarn) == 0


def test_anotar_falhas_anteriores_so_com_falhas():
    com_falhas = _http_error(401)
    anotar_falhas_anteriores(com_falhas, ["doc 1: http_404"], "download(s) de documento")
    assert com_falhas.__notes__ == [
        "Antes do 401, 1 download(s) de documento falharam. Falhas: doc 1: http_404."
    ]

    sem_falhas = _http_error(401)
    anotar_falhas_anteriores(sem_falhas, [], "download(s) de documento")
    assert not hasattr(sem_falhas, "__notes__")


@pytest.mark.parametrize(
    ("exc", "esperado"),
    [
        (_http_error(401), True),
        (_http_error(403), False),
        (requests.HTTPError("sem resposta"), False),
        (RetryExhaustedError(401, 3), False),
        (requests.Timeout(), False),
    ],
)
def test_e_token_invalido(exc, esperado):
    assert e_token_invalido(exc) is esperado
    assert STATUS_TOKEN_INVALIDO == 401


@pytest.mark.parametrize(
    "exc",
    [
        _http_error(500),
        RetryExhaustedError(503, 3),
        requests.ReadTimeout(),
        requests.ConnectTimeout(),
        requests.ConnectionError(),
        InvalidJSONResponseError("https://example.test", 200, 3),
        BotChallengeBlockedError("TRF3", "https://example.test"),
        WafChallengeError("TJPE", "https://example.test"),
    ],
)
def test_excecoes_de_falha_por_linha_tem_motivo(exc):
    """Toda exceção capturada como linha tem motivo no vocabulário."""
    assert isinstance(exc, EXCECOES_DE_FALHA_POR_LINHA)
    motivo_falha(exc)


@pytest.mark.parametrize(
    "exc",
    # ``requests.JSONDecodeError`` tem motivo, mas fica fora da tupla para não
    # mudar o que JusBR, PDPJ e eSAJ capturam como linha.
    [
        requests.TooManyRedirects(), requests.exceptions.InvalidURL(), ValueError(),
        requests.JSONDecodeError("Expecting value", "", 0),
    ],
)
def test_excecoes_fora_do_vocabulario_nao_viram_linha(exc):
    assert not isinstance(exc, EXCECOES_DE_FALHA_POR_LINHA)


def test_status_consulta_falha():
    assert STATUS_CONSULTA_FALHA == "Falha na consulta"
