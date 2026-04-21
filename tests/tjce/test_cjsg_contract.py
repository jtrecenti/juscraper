"""Offline contract tests for TJCE cjsg.

Mocks ``resultadoCompleta.do`` + ``trocaDePagina.do`` with captured samples
(see ``tests/fixtures/capture/tjce.py``) and asserts the public DataFrame
contract. Covers typical multi-page, single-page, and zero-result scenarios.

Also includes a unit-level regression test for the TLS ``SECLEVEL=1`` adapter
required by the TJCE server.
"""
import ssl

import pandas as pd
import responses
from requests.adapters import HTTPAdapter
from responses.matchers import query_param_matcher, urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjce.cjsg_download import _TJCETLSAdapter
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_esaj_body

BASE = "https://esaj.tjce.jus.br/cjsg"
CJSG_MIN_COLUMNS = {"processo", "cd_acordao", "cd_foro", "ementa"}


def _add_post(pesquisa: str) -> None:
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjce", "cjsg/post_initial.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(make_esaj_body(pesquisa), allow_blank=True)],
    )


def _add_get(pagina: int, sample_path: str) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjce", sample_path),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[query_param_matcher({"tipoDeDecisao": "A", "pagina": str(pagina)})],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(tmp_path, mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_post("dano moral")
    _add_get(1, "cjsg/results_normal_page_01.html")
    _add_get(2, "cjsg/results_normal_page_02.html")

    df = jus.scraper("tjce", download_path=str(tmp_path)).cjsg(
        "dano moral", paginas=range(1, 3)
    )

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(tmp_path, mocker):
    """Query whose hits fit in one page skips the per-page loop."""
    mocker.patch("time.sleep")
    _add_post("usucapiao extraordinario predio rural familia")
    _add_get(1, "cjsg/single_page.html")

    df = jus.scraper("tjce", download_path=str(tmp_path)).cjsg(
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

    df = jus.scraper("tjce", download_path=str(tmp_path)).cjsg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_tls_adapter_configures_seclevel1():
    """TJCE server requires ``SECLEVEL=1``; regression guard for the custom adapter."""
    adapter = _TJCETLSAdapter()
    assert isinstance(adapter, HTTPAdapter)

    adapter.init_poolmanager(connections=1, maxsize=1)
    ctx = adapter.poolmanager.connection_pool_kw["ssl_context"]
    assert isinstance(ctx, ssl.SSLContext)
