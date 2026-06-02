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
import responses

import juscraper as jus
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
def test_cpopg_raises_when_captcha_keeps_failing(monkeypatch):
    """After ``max_captcha_attempts`` rejections, surface the error."""
    for _ in range(3):
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

    from juscraper.courts.trf6 import download

    monkeypatch.setattr(download, "solve_captcha", lambda b64: "wrong")

    scraper = jus.scraper("trf6", sleep_time=0, max_captcha_attempts=3)
    with pytest.raises(RuntimeError, match="captcha solver failed"):
        scraper.cpopg("10052295520234063801")


def test_cpopg_rejects_unknown_kwargs():
    """Passing an unknown kwarg surfaces as a friendly ``TypeError``."""
    scraper = jus.scraper("trf6", sleep_time=0)
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg("10052295520234063801", filtro_inexistente="x")
