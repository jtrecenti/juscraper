"""Offline contract tests for TRF6 ``cpopg`` (eproc consulta pública).

The captcha solver is mocked out (it would otherwise need to download a
HuggingFace model) — we patch :func:`juscraper.courts.trf6.download.solve_captcha`
to return a fixed string, so the contract test stays fully offline. The
captcha **content** that ends up in the POST body is asserted via the
custom subset matcher so the request shape is locked down.
"""
from __future__ import annotations

from urllib.parse import parse_qsl

import pandas as pd
import pytest
import requests
import responses

import juscraper as jus
from juscraper.core.exceptions import BloqueioAntiBotWarning, BotChallengeBlockedError
from tests._helpers import load_sample_bytes

GET_URL = "https://eproc1g.trf6.jus.br/eproc/externo_controlador.php"
GET_PARAMS = {"acao": "processo_consulta_publica"}
POST_URL = "https://eproc1g.trf6.jus.br/eproc/externo_controlador.php"
POST_PARAMS = {
    "acao": "processo_consulta_publica",
    "acao_origem": "principal",
    "acao_retorno": "processo_consulta_publica",
}

FAKE_CAPTCHA = "abc1"


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
def test_cpopg_missing_process_returns_row_with_only_id_cnj(fake_captcha_solver):
    """When the CNJ doesn't match, eproc re-serves the form (no detail)."""
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
    assert pd.isna(row.get("processo")) or row.get("processo") is None
    # Ausente da consulta pública não é falha da requisição.
    assert row["motivo_falha"] is None


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
    """Captcha recusado ``max_captcha_attempts`` vezes: a linha sai ``resposta_inesperada``; o 2º CNJ é consultado."""
    for _ in range(3):
        responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", "cpopg/form_initial.html"))
        responses.add(responses.POST, POST_URL, body=load_sample_bytes("trf6", "cpopg/search_bad_captcha.html"))
    responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", "cpopg/form_initial.html"))
    responses.add(responses.POST, POST_URL, body=load_sample_bytes("trf6", "cpopg/detail_normal.html"))

    from juscraper.courts.trf6 import download

    monkeypatch.setattr(download, "solve_captcha", lambda b64: "wrong")

    scraper = jus.scraper("trf6", sleep_time=0, max_captcha_attempts=3)
    with pytest.warns(UserWarning, match="processo 00000000020994060000: resposta_inesperada"):
        df = scraper.cpopg(["00000000020994060000", "10052295520234063801"])

    assert list(df["motivo_falha"]) == ["resposta_inesperada", None]
    assert pd.isna(df.iloc[0]["processo"])
    assert df.iloc[1]["processo"] == "1005229-55.2023.4.06.3801"


@responses.activate
def test_cpopg_nao_envia_user_agent_de_navegador(fake_captcha_solver):
    """O F5 do portal desafia user agents ``Mozilla/...``; a sessão usa o padrão do ``requests``."""
    responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", "cpopg/form_initial.html"))
    responses.add(responses.POST, POST_URL, body=load_sample_bytes("trf6", "cpopg/detail_normal.html"))

    scraper = jus.scraper("trf6", sleep_time=0)
    scraper.cpopg("10052295520234063801")

    for call in responses.calls:
        assert not call.request.headers["User-Agent"].startswith("Mozilla/")


@responses.activate
def test_cpopg_desafio_f5_encerra_o_lote_com_bloqueio_anti_bot(fake_captcha_solver):
    """O desafio do F5 no lugar do formulário: o 1º CNJ e os seguintes saem ``bloqueio_anti_bot``, sem novos pedidos."""
    responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", "cpopg/form_desafio_f5.html"))

    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.warns(BloqueioAntiBotWarning, match="2 consulta.*bloqueio_anti_bot"):
        df = scraper.cpopg(["10052295520234063801", "00000000020994060000"])

    assert list(df["motivo_falha"]) == ["bloqueio_anti_bot", "bloqueio_anti_bot"]
    assert len(responses.calls) == 1


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
    responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", "cpopg/form_initial.html"))
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
