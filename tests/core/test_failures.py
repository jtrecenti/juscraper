"""Testes de ``juscraper.core.failures``: o vocabulário do motivo, o aviso agregado e a nota do 401."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import NamedTuple

import pytest
import requests

from juscraper.core import failures
from juscraper.core.exceptions import (
    BloqueioAntiBotWarning,
    BotChallengeBlockedError,
    CaptchaEsgotadoError,
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
    avisar_falhas_de_processos,
    consultar_em_lote,
    consultar_processo,
    e_token_invalido,
    linhas_de_processos,
    motivo_falha,
    motivo_falha_ou_inesperada,
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
        (requests.exceptions.ChunkedEncodingError(), "conexao"),
        (requests.exceptions.ContentDecodingError(), "resposta_inesperada"),
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
        "captcha_esgotado",
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


def test_avisar_falhas_fecha_com_a_consequencia_pedida():
    with pytest.warns(UserWarning, match=r"falharam\. Falhas: peça 1: http_404\. Veja a coluna x\.$"):
        avisar_falhas(["peça 1: http_404"], "Scraper.metodo", "download(s) de peça", "Veja a coluna x.")


def test_motivo_falha_ou_inesperada():
    assert motivo_falha_ou_inesperada(_http_error(404)) == "http_404"
    assert motivo_falha_ou_inesperada(requests.TooManyRedirects()) == "resposta_inesperada"
    assert motivo_falha_ou_inesperada(ValueError("layout")) == "resposta_inesperada"


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
        requests.exceptions.ChunkedEncodingError(),
        requests.exceptions.ContentDecodingError(),
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


class _Consulta(NamedTuple):
    html: str | None
    motivo: str | None
    pecas: list[str]


def test_consultar_em_lote_para_no_bloqueio_e_preenche_os_seguintes(monkeypatch):
    """O CNJ bloqueado encerra o lote; os seguintes não são consultados e recebem cada um o seu resultado."""
    pausas: list[float] = []
    monkeypatch.setattr(failures, "time", SimpleNamespace(sleep=pausas.append))
    motivos = {"a": None, "b": "http_500", "c": "bloqueio_anti_bot"}
    consultados: list[str] = []

    def consultar(cnj: str) -> _Consulta:
        consultados.append(cnj)
        return _Consulta(cnj if motivos[cnj] is None else None, motivos[cnj], [])

    consultas = consultar_em_lote(
        ["a", "b", "c", "d", "e"],
        consultar,
        lambda motivo: _Consulta(None, motivo, []),
        sleep_time=0.5,
    )

    assert consultados == ["a", "b", "c"]
    assert [c.motivo for c in consultas] == [None, "http_500", *["bloqueio_anti_bot"] * 3]
    assert pausas == [0.5, 0.5]  # entre a/b e b/c; nada depois do bloqueio
    assert consultas[3].pecas is not consultas[4].pecas


def test_consultar_em_lote_sem_pausa_depois_do_ultimo(monkeypatch):
    pausas: list[float] = []
    monkeypatch.setattr(failures, "time", SimpleNamespace(sleep=pausas.append))
    consultas = consultar_em_lote(
        ["a", "b"], lambda cnj: _Consulta(cnj, None, []), lambda motivo: _Consulta(None, motivo, []), sleep_time=1
    )
    assert [c.html for c in consultas] == ["a", "b"]
    assert pausas == [1]


def test_consultar_em_lote_encerrar_preenche_com_o_motivo_da_ultima():
    """``encerrar`` vê as consultas feitas; os CNJs seguintes recebem o motivo da que encerrou."""
    vistas: list[int] = []

    def encerrar(consultas: list[_Consulta]) -> bool:
        vistas.append(len(consultas))
        return [c.motivo for c in consultas[-2:]] == ["captcha_esgotado"] * 2

    consultas = consultar_em_lote(
        ["a", "b", "c", "d"],
        lambda _cnj: _Consulta(None, "captcha_esgotado", []),
        lambda motivo: _Consulta(None, motivo, []),
        sleep_time=0,
        encerrar=encerrar,
    )
    assert vistas == [1, 2]
    assert [c.motivo for c in consultas] == ["captcha_esgotado"] * 4


def _parse(html: str) -> dict[str, str]:
    if html == "quebrado":
        raise ValueError("layout novo")
    return {"processo": html}


def test_linhas_de_processos():
    """Parse ok, download que falhou e HTML recusado (sem e com motivo do download) viram uma linha cada."""
    linhas = linhas_de_processos(
        ["1", "2", "3", "4"],
        ["ok", None, "quebrado", "quebrado"],
        [None, "timeout", None, "bloqueio_anti_bot"],
        parse=_parse,
        logger=logging.getLogger("teste"),
    )
    assert linhas == [
        {"processo": "ok", "id_cnj": "1", COLUNA_MOTIVO_FALHA: None},
        {"id_cnj": "2", COLUNA_MOTIVO_FALHA: "timeout"},
        {"id_cnj": "3", COLUNA_MOTIVO_FALHA: "resposta_inesperada"},
        {"id_cnj": "4", COLUNA_MOTIVO_FALHA: "bloqueio_anti_bot"},
    ]


def test_avisar_falhas_de_processos():
    esperado = r"X\.cpopg: 1 consulta\(s\) de processo falharam. Falhas: processo 2: timeout\."
    with pytest.warns(UserWarning, match=esperado):
        avisar_falhas_de_processos(["1", "2"], [None, "timeout"], "X.cpopg")


def test_avisar_falhas_de_processos_sem_falha_nao_avisa(recwarn):
    avisar_falhas_de_processos(["1"], [None], "X.cpopg")
    assert not recwarn.list


def _buscar(erro: BaseException | None, html: str | None = None):
    def buscar(_cnj: str) -> str | None:
        if erro is not None:
            raise erro
        return html

    return buscar


@pytest.mark.parametrize(
    ("buscar", "esperado"),
    [
        (_buscar(None, "<html>"), ("<html>", None)),
        (_buscar(None), (None, None)),
        (_buscar(BotChallengeBlockedError("TRF6", "https://example.test")), (None, "bloqueio_anti_bot")),
        (_buscar(requests.ReadTimeout()), (None, "timeout")),
        (_buscar(CaptchaEsgotadoError("TRF6: captcha recusado")), (None, "captcha_esgotado")),
        (_buscar(RuntimeError("formulário sem captcha")), (None, "resposta_inesperada")),
    ],
)
def test_consultar_processo(buscar, esperado):
    assert consultar_processo(buscar, "1", tribunal="TRF6", logger=logging.getLogger("teste")) == esperado


def test_consultar_processo_propaga_import_error():
    with pytest.raises(ImportError):
        consultar_processo(_buscar(ImportError("txtcaptcha")), "1", tribunal="TRF6", logger=logging.getLogger("t"))
