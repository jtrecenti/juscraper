"""Offline contract tests for TJSP cjsg.

Mocks ``cjsg/resultadoCompleta.do`` (POST) + ``cjsg/trocaDePagina.do`` (GET)
with samples captured by ``tests/fixtures/capture/tjsp.py``. Validates the
public DataFrame contract and the POST body payload.

Also covers the pre-request guard that raises ``QueryTooLongError`` when
``pesquisa`` exceeds 120 characters — exercising it without any HTTP
interaction.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher, urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjsp.exceptions import QueryTooLongError
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_tjsp_cjsg_body

BASE = "https://esaj.tjsp.jus.br/cjsg"
CJSG_MIN_COLUMNS = {"processo", "cd_acordao", "cd_foro", "ementa"}


def _add_post(pesquisa: str) -> None:
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjsp", "cjsg/post_initial.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(make_tjsp_cjsg_body(pesquisa), allow_blank=True)],
    )


def _add_get(pagina: int, sample_path: str, *, conversation_id: str | None = None) -> None:
    params = {"tipoDeDecisao": "A", "pagina": str(pagina)}
    if conversation_id is not None:
        params["conversationId"] = conversation_id
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjsp", sample_path),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[query_param_matcher(params)],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(tmp_path, mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_post("dano moral")
    # Page 1 is fetched without conversationId; page 2 reuses it when the
    # first-page HTML exposes ``<input name='conversationId' value='...'>``.
    # Match the common case: page 1 has no conversationId, page 2 has it.
    _add_get(1, "cjsg/results_normal_page_01.html")
    _add_get(2, "cjsg/results_normal_page_02.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "dano moral", paginas=range(1, 3)
    )

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(tmp_path, mocker):
    """Query whose hits fit in a single page skips the per-page loop."""
    mocker.patch("time.sleep")
    _add_post("usucapiao extraordinario predio rural familia")
    _add_get(1, "cjsg/single_page.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "usucapiao extraordinario predio rural familia", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(tmp_path, mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_post("juscraper_probe_zero_hits_xyzqwe")
    _add_get(1, "cjsg/no_results.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_cjsg_query_too_long_raises(tmp_path):
    """Pre-request guard: a pesquisa > 120 chars must raise before any HTTP."""
    pesquisa = "a" * 121
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(QueryTooLongError):
        scraper.cjsg(pesquisa, paginas=1)
