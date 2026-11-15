"""Offline contract tests for TRF6 ``cpopg`` (eproc consulta pública).

The captcha solver is mocked out (it would otherwise need to download a
HuggingFace model) — we patch :func:`juscraper.courts.trf6.download.solve_captcha`
to return a fixed string, so the contract test stays fully offline. The
captcha **content** that ends up in the POST body is asserted via the
custom subset matcher so the request shape is locked down.
"""
from __future__ import annotations

import warnings
from urllib.parse import parse_qsl

import numpy as np
import pandas as pd
import pytest
import requests
import responses

import juscraper as jus
from juscraper.core.exceptions import BloqueioAntiBotWarning, BotChallengeBlockedError
from juscraper.courts.trf6.parse import COLUNAS_DETALHE, parse_detail
from tests._helpers import load_sample, load_sample_bytes

GET_URL = "https://eproc1g.trf6.jus.br/eproc/externo_controlador.php"
GET_PARAMS = {"acao": "processo_consulta_publica"}
POST_URL = "https://eproc1g.trf6.jus.br/eproc/externo_controlador.php"
POST_PARAMS = {
    "acao": "processo_consulta_publica",
    "acao_origem": "principal",
    "acao_retorno": "processo_consulta_publica",
}

FAKE_CAPTCHA = "abc1"


def _form(sample: str = "cpopg/form_initial.html") -> None:
    """Registra uma resposta ao GET do formulário."""
    responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", sample))


def _busca(sample: str) -> None:
    """Registra uma resposta ao POST da busca, a partir de um sample."""
    responses.add(responses.POST, POST_URL, body=load_sample_bytes("trf6", sample))


def _subset_form_matcher(expected: dict[str, str]):
    """``responses`` 0.x lacks ``strict_match`` — homemade subset matcher."""

    def _match(request) -> tuple[bool, str]:
        body = request.body or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        actual = dict(parse_qsl(body, keep_blank_values=True))
        for key, value in expected.items():
            if actual.get(key) != value:
                return False, (
                    f"expected {key!r}={value!r}, got {actual.get(key)!r}"
                )
        return True, ""

    return _match


@pytest.fixture
def fake_captcha_solver(monkeypatch):
    """Replace the txtcaptcha-backed solver with a deterministic stub."""
    from juscraper.courts.trf6 import download

    monkeypatch.setattr(download, "solve_captcha", lambda b64: FAKE_CAPTCHA)
    return FAKE_CAPTCHA


@responses.activate
def test_cpopg_returns_dataframe_with_canonical_columns(fake_captcha_solver):
    """Happy path: form fetch + captcha + search + parse → populated row."""
    responses.add(
        responses.GET,
        GET_URL,
        body=load_sample_bytes("trf6", "cpopg/form_initial.html"),
        match=[responses.matchers.query_param_matcher(GET_PARAMS)],
    )
    responses.add(
        responses.POST,
        POST_URL,
        body=load_sample_bytes("trf6", "cpopg/detail_normal.html"),
        match=[
            responses.matchers.query_param_matcher(POST_PARAMS),
            _subset_form_matcher(
                {
                    "txtNumProcesso": "1005229-55.2023.4.06.3801",
                    "txtInfraCaptcha": fake_captcha_solver,
                    "sbmNovo": "Consultar",
                }
            ),
        ],
    )

    scraper = jus.scraper("trf6", sleep_time=0)
    df = scraper.cpopg("10052295520234063801")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    expected = {
        "id_cnj",
        "processo",
        "classe",
        "data_autuacao",
        "situacao",
        "magistrado",
        "orgao_julgador",
        "assuntos",
        "polo_ativo",
        "polo_passivo",
        "movimentacoes",
    }
    assert expected <= set(df.columns)
    row = df.iloc[0]
    assert row["id_cnj"] == "10052295520234063801"
    assert row["processo"] == "1005229-55.2023.4.06.3801"
    assert isinstance(row["polo_ativo"], list) and row["polo_ativo"]
    assert isinstance(row["movimentacoes"], list) and row["movimentacoes"]


@responses.activate
def test_cpopg_missing_process_keeps_detail_columns_empty(fake_captcha_solver):
    """CNJ ausente (o eproc devolve o formulário, sem detalhe) sai numa linha com ``id_cnj``.

    As colunas do detalhe continuam no DataFrame, com ``None``, mesmo quando
    nenhum CNJ do lote foi lido (mesmo sintoma do #442 no TRF5).
    """
    responses.add(
        responses.GET,
        GET_URL,
        body=load_sample_bytes("trf6", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        POST_URL,
        body=load_sample_bytes("trf6", "cpopg/search_no_results.html"),
    )

    scraper = jus.scraper("trf6", sleep_time=0)
    df = scraper.cpopg("00000000020994060000")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == "00000000020994060000"
    assert list(df.columns) == [*COLUNAS_DETALHE, "id_cnj", "motivo_falha"]
    assert all(v is None for v in df[list(COLUNAS_DETALHE)].to_numpy().ravel())
    # Ausente da consulta pública não é falha da requisição.
    assert row["motivo_falha"] is None


@responses.activate
def test_cpopg_lote_sem_nenhuma_resposta_mantem_colunas_do_detalhe(fake_captcha_solver):
    """Falha de requisição em todo o lote: colunas do detalhe com ``None``, motivo na linha."""
    responses.add(responses.GET, GET_URL, body=requests.exceptions.ConnectionError("recusada"))
    responses.add(responses.GET, GET_URL, body=requests.exceptions.ConnectionError("recusada"))

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.warns(UserWarning, match="conexao"):
        df = scraper.cpopg(["00000000020994060000", "10052295520234063801"])

    assert list(df.columns) == [*COLUNAS_DETALHE, "id_cnj", "motivo_falha"]
    assert list(df["motivo_falha"]) == ["conexao", "conexao"]
    assert all(v is None for v in df[list(COLUNAS_DETALHE)].to_numpy().ravel())


def test_cpopg_parse_sem_html_mantem_colunas_do_detalhe():
    """``cpopg_parse`` só com ``None`` sai com as colunas do detalhe em ``None``."""
    scraper = jus.scraper("trf6", sleep_time=0)
    df = scraper.cpopg_parse([None], ["00000000020994060000"])
    assert list(df.columns) == [*COLUNAS_DETALHE, "id_cnj"]
    assert all(v is None for v in df[list(COLUNAS_DETALHE)].to_numpy().ravel())


@pytest.mark.parametrize("sample", ["cpopg/detail_normal.html", "cpopg/detail_cumprimento_sentenca.html"])
def test_colunas_detalhe_sao_as_chaves_de_parse_detail(sample):
    """``COLUNAS_DETALHE`` acompanha o registro de ``parse_detail``, na mesma ordem."""
    record = parse_detail(load_sample("trf6", sample, encoding="latin-1"))
    assert tuple(record) == COLUNAS_DETALHE


@responses.activate
def test_cpopg_falha_de_requisicao_vira_motivo_e_o_lote_segue(fake_captcha_solver):
    """HTTP 500 na busca do 1º CNJ: a linha sai com ``http_500`` e aviso; o 2º é consultado."""
    responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", "cpopg/form_initial.html"))
    responses.add(responses.POST, POST_URL, status=500)
    responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", "cpopg/form_initial.html"))
    responses.add(responses.POST, POST_URL, body=load_sample_bytes("trf6", "cpopg/detail_normal.html"))

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.warns(UserWarning, match="processo 00000000020994060000: http_500"):
        df = scraper.cpopg(["00000000020994060000", "10052295520234063801"])

    assert list(df["id_cnj"]) == ["00000000020994060000", "10052295520234063801"]
    assert list(df["motivo_falha"]) == ["http_500", None]
    assert pd.isna(df.iloc[0]["processo"])
    assert df.iloc[1]["processo"] == "1005229-55.2023.4.06.3801"


@responses.activate
def test_cpopg_download_avisa_falha_de_requisicao(fake_captcha_solver):
    """``cpopg_download`` devolve ``None`` para a requisição que falhou e avisa o motivo."""
    responses.add(responses.GET, GET_URL, body=requests.exceptions.ConnectionError("recusada"))

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.warns(UserWarning, match="TRF6Scraper.cpopg_download: 1 consulta.*conexao"):
        htmls = scraper.cpopg_download("10052295520234063801")
    assert htmls == [None]


@responses.activate
def test_cpopg_retries_on_captcha_failure(monkeypatch):
    """When the first captcha is rejected, the scraper fetches a fresh one."""
    # Two form GETs (initial + retry) and two POSTs (rejected + accepted).
    responses.add(
        responses.GET,
        GET_URL,
        body=load_sample_bytes("trf6", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        POST_URL,
        body=load_sample_bytes("trf6", "cpopg/search_bad_captcha.html"),
    )
    responses.add(
        responses.GET,
        GET_URL,
        body=load_sample_bytes("trf6", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        POST_URL,
        body=load_sample_bytes("trf6", "cpopg/detail_normal.html"),
    )

    # Solver returns a different value each call so the assertion below
    # confirms BOTH attempts ran.
    calls = []

    def fake_solve(b64):
        calls.append(b64[:10])
        return f"sol{len(calls)}"

    from juscraper.courts.trf6 import download

    monkeypatch.setattr(download, "solve_captcha", fake_solve)

    scraper = jus.scraper("trf6", sleep_time=0, max_captcha_attempts=3)
    df = scraper.cpopg("10052295520234063801")
    assert len(calls) == 2  # the retry actually fired
    assert df.iloc[0]["processo"] == "1005229-55.2023.4.06.3801"


@responses.activate
def test_cpopg_captcha_esgotado_vira_linha_e_o_lote_segue(monkeypatch):
    """Captcha recusado ``max_captcha_attempts`` vezes: a linha sai ``captcha_esgotado``; o 2º CNJ é consultado."""
    for _ in range(3):
        _form()
        _busca("cpopg/search_bad_captcha.html")
    _form()
    _busca("cpopg/detail_normal.html")

    from juscraper.courts.trf6 import download

    monkeypatch.setattr(download, "solve_captcha", lambda b64: "wrong")

    scraper = jus.scraper("trf6", sleep_time=0, max_captcha_attempts=3)
    with pytest.warns(UserWarning, match="processo 00000000020994060000: captcha_esgotado"):
        df = scraper.cpopg(["00000000020994060000", "10052295520234063801"])

    assert list(df["motivo_falha"]) == ["captcha_esgotado", None]
    assert pd.isna(df.iloc[0]["processo"])
    assert df.iloc[1]["processo"] == "1005229-55.2023.4.06.3801"


CNJS = ["00000000020994060000", "00000000030994060000", "00000000040994060000", "10052295520234063801"]


@responses.activate
@pytest.mark.parametrize(("limite", "consultados"), [(2, 2), (3, 3), (None, 4)])
def test_cpopg_captcha_errando_sempre_encerra_o_lote(fake_captcha_solver, limite, consultados):
    """Após ``max_captcha_esgotado_seguidos`` CNJs com captcha esgotado, os seguintes saem sem consulta."""
    for _ in range(consultados):
        _form()
        _busca("cpopg/search_bad_captcha.html")

    scraper = jus.scraper("trf6", sleep_time=0, max_captcha_attempts=1, max_captcha_esgotado_seguidos=limite)
    with pytest.warns(UserWarning, match="4 consulta.*captcha_esgotado"):
        df = scraper.cpopg(CNJS)

    assert list(df["motivo_falha"]) == ["captcha_esgotado"] * 4
    assert len(responses.calls) == 2 * consultados  # form + busca por CNJ consultado


@responses.activate
def test_cpopg_captcha_que_volta_a_acertar_zera_a_contagem(fake_captcha_solver):
    """O limite conta CNJs seguidos: um acerto no meio zera a contagem, e o lote vai até o fim."""
    for sample in ["search_bad_captcha", "detail_normal", "search_bad_captcha", "detail_normal"]:
        _form()
        _busca(f"cpopg/{sample}.html")

    scraper = jus.scraper("trf6", sleep_time=0, max_captcha_attempts=1, max_captcha_esgotado_seguidos=2)
    with pytest.warns(UserWarning, match="2 consulta.*captcha_esgotado"):
        df = scraper.cpopg(CNJS)

    assert list(df["motivo_falha"]) == ["captcha_esgotado", None, "captcha_esgotado", None]


@responses.activate
def test_cpopg_sem_polos_avisa_uma_vez_ao_fim(fake_captcha_solver):
    """Sem a faixa dos polos nem AUTOR/RÉU: polos vazios, a linha fica, e um aviso agregado sai ao fim."""
    detalhe = load_sample_bytes("trf6", "cpopg/detail_cumprimento_sentenca.html").replace(
        b'<th class="infraTh" width="50%">EXEQUENTE</th><th class="infraTh" width="50%">EXECUTADO</th>',
        b'<th class="infraTh" colspan="2">EXEQUENTE</th>',
    )
    for _ in range(2):
        _form()
        responses.add(responses.POST, POST_URL, body=detalhe)

    scraper = jus.scraper("trf6", sleep_time=0)
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        df = scraper.cpopg(["10052295520234063801", "10052295520234063801"])

    assert [str(a.message) for a in avisos] == [
        "TRF6Scraper.cpopg: 2 processo(s) sem polo ativo nem passivo (10052295520234063801, 10052295520234063801). "
        "A tabela de partes não traz a faixa dos polos nem os rótulos AUTOR/RÉU; polo_ativo e polo_passivo "
        "saem vazios."
    ]
    assert list(df["processo"]) == ["1005229-55.2023.4.06.3801"] * 2
    assert list(df["motivo_falha"]) == [None, None]


@pytest.mark.parametrize("parametro", ["max_captcha_attempts", "max_captcha_esgotado_seguidos"])
@pytest.mark.parametrize("limite", [0, -1])
def test_limite_de_captcha_menor_que_um(parametro, limite):
    with pytest.raises(ValueError, match=parametro):
        jus.scraper("trf6", **{parametro: limite})


@pytest.mark.parametrize("parametro", ["max_captcha_attempts", "max_captcha_esgotado_seguidos"])
@pytest.mark.parametrize("limite", ["3", 2.5, 3.0, True])
def test_limite_de_captcha_fora_de_int(parametro, limite):
    with pytest.raises(TypeError, match=parametro):
        jus.scraper("trf6", **{parametro: limite})


def test_max_captcha_attempts_nao_aceita_none():
    with pytest.raises(TypeError, match="max_captcha_attempts"):
        jus.scraper("trf6", max_captcha_attempts=None)


def test_limite_de_captcha_aceita_inteiro_do_numpy():
    scraper = jus.scraper("trf6", max_captcha_attempts=np.int64(2), max_captcha_esgotado_seguidos=np.int64(4))
    assert (scraper.max_captcha_attempts, scraper.max_captcha_esgotado_seguidos) == (2, 4)


def test_max_captcha_esgotado_seguidos_none_desliga():
    assert jus.scraper("trf6", max_captcha_esgotado_seguidos=None).max_captcha_esgotado_seguidos is None


@responses.activate
def test_cpopg_nao_envia_user_agent_de_navegador(fake_captcha_solver):
    """O F5 do portal desafia user agents ``Mozilla/...``; a sessão usa o padrão do ``requests``."""
    _form()
    _busca("cpopg/detail_normal.html")

    scraper = jus.scraper("trf6", sleep_time=0)
    scraper.cpopg("10052295520234063801")

    for call in responses.calls:
        assert not call.request.headers["User-Agent"].startswith("Mozilla/")


@responses.activate
def test_cpopg_desafio_f5_encerra_o_lote_com_bloqueio_anti_bot(fake_captcha_solver):
    """O desafio do F5 no lugar do formulário: o 1º CNJ e os seguintes saem ``bloqueio_anti_bot``, sem novos pedidos."""
    _form("cpopg/form_desafio_f5.html")

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.warns(BloqueioAntiBotWarning, match="2 consulta.*bloqueio_anti_bot"):
        df = scraper.cpopg(["10052295520234063801", "00000000020994060000"])

    assert list(df["motivo_falha"]) == ["bloqueio_anti_bot", "bloqueio_anti_bot"]
    assert len(responses.calls) == 1


@responses.activate
def test_cpopg_desafio_f5_na_busca_tambem_encerra_o_lote(fake_captcha_solver):
    """O desafio do F5 na resposta do POST não passa por processo ausente."""
    _form()
    _busca("cpopg/form_desafio_f5.html")

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.warns(BloqueioAntiBotWarning):
        df = scraper.cpopg(["10052295520234063801", "00000000020994060000"])

    assert list(df["motivo_falha"]) == ["bloqueio_anti_bot", "bloqueio_anti_bot"]
    assert len(responses.calls) == 2


@responses.activate
def test_cpopg_pagina_desconhecida_na_busca_vira_resposta_inesperada(fake_captcha_solver):
    """Uma página que não é detalhe nem formulário (manutenção, erro) não passa por processo ausente."""
    _form()
    responses.add(responses.POST, POST_URL, body="<html><body>Sistema em manutenção</body></html>")

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.warns(UserWarning, match="processo 10052295520234063801: resposta_inesperada"):
        df = scraper.cpopg("10052295520234063801")

    assert list(df["motivo_falha"]) == ["resposta_inesperada"]


def test_desafio_f5_tem_mensagem_propria():
    """A mensagem fala do desafio JavaScript do F5, não do 403 do Akamai."""
    from juscraper.courts.trf6.download import DesafioF5Error

    erro = DesafioF5Error("https://eproc1g.trf6.jus.br/eproc/")
    assert isinstance(erro, BotChallengeBlockedError)
    assert "F5" in str(erro) and "desafio JavaScript" in str(erro)
    assert "403" not in str(erro)


@responses.activate
def test_cpopg_txtcaptcha_ausente_propaga(monkeypatch):
    """Sem o ``txtcaptcha``, nenhum CNJ passaria: o ``ImportError`` sobe em vez de virar linha."""
    _form()
    from juscraper.courts.trf6 import download

    def sem_txtcaptcha(b64):
        raise ImportError("txtcaptcha")

    monkeypatch.setattr(download, "solve_captcha", sem_txtcaptcha)

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.raises(ImportError):
        scraper.cpopg("10052295520234063801")


def test_cpopg_parse_html_fora_do_formato_vira_linha(monkeypatch):
    """Um HTML que o parser recusa vira linha só com ``id_cnj``, com aviso; os demais são lidos."""
    from juscraper.courts.trf6 import client

    detalhe = load_sample_bytes("trf6", "cpopg/detail_normal.html").decode("latin-1")
    original = client.parse_detail

    def parse_que_recusa(html):
        if html == "quebrado":
            raise ValueError("layout novo")
        return original(html)

    monkeypatch.setattr(client, "parse_detail", parse_que_recusa)

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.warns(UserWarning, match="cpopg_parse: 1 consulta.*processo 00000000020994060000: resposta_inesperada"):
        df = scraper.cpopg_parse(["quebrado", detalhe], ["00000000020994060000", "10052295520234063801"])

    assert list(df["id_cnj"]) == ["00000000020994060000", "10052295520234063801"]
    assert "motivo_falha" not in df.columns
    assert pd.isna(df.iloc[0]["processo"])
    assert df.iloc[1]["processo"] == "1005229-55.2023.4.06.3801"


def test_cpopg_rejects_unknown_kwargs():
    """Passing an unknown kwarg surfaces as a friendly ``TypeError``."""
    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg("10052295520234063801", filtro_inexistente="x")
