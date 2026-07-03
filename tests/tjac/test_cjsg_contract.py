"""Offline contract tests for TJAC cjsg.

Mocks ``resultadoCompleta.do`` + ``trocaDePagina.do`` with captured samples
(see ``tests/fixtures/capture/tjac.py``) and asserts the public DataFrame
contract. Covers typical multi-page, single-page, and zero-result scenarios.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher, urlencoded_params_matcher

import juscraper as jus
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_esaj_body

BASE = "https://esaj.tjac.jus.br/cjsg"
CJSG_MIN_COLUMNS = {"processo", "cd_acordao", "cd_foro", "ementa"}


def _add_post(pesquisa: str) -> None:
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjac", "cjsg/post_initial.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(make_esaj_body(pesquisa), allow_blank=True)],
    )


def _add_get(pagina: int, sample_path: str) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjac", sample_path),
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

    df = jus.scraper("tjac", download_path=str(tmp_path)).cjsg(
        "dano moral", paginas=range(1, 3)
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(tmp_path, mocker):
    """Query whose hits fit in one page skips the per-page loop."""
    mocker.patch("time.sleep")
    _add_post("usucapiao extraordinario predio rural familia")
    _add_get(1, "cjsg/single_page.html")

    df = jus.scraper("tjac", download_path=str(tmp_path)).cjsg(
        "usucapiao extraordinario predio rural familia", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(tmp_path, mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_post("juscraper_probe_zero_hits_xyzqwe")
    _add_get(1, "cjsg/no_results.html")

    df = jus.scraper("tjac", download_path=str(tmp_path)).cjsg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_count_only_via_esaj_base(tmp_path, mocker):
    """Smoke: ``count_only=True`` em TJAC funciona via base eSAJ (issue #92).

    Confirma que o ramo count_only declarado em :class:`EsajSearchScraper`
    nao depende do override TJSP — vale tambem para TJAC/TJAL/TJAM/TJCE/
    TJMS que herdam direto.
    """
    mocker.patch("time.sleep")
    _add_post("dano moral")
    _add_get(1, "cjsg/results_normal_page_01.html")

    n = jus.scraper("tjac", download_path=str(tmp_path)).cjsg(
        "dano moral", count_only=True,
    )

    assert isinstance(n, int)
    assert n == 13929  # totalResultadoAbaRetornoFiltro-A no sample
    assert len(responses.calls) == 2  # POST + 1 GET, sem pagina 2


def test_cjsg_count_only_rejects_long_data_publicacao_window(tmp_path):
    """count_only=True com data_publicacao_* > 366d levanta ValueError (#92).

    O auto-chunk so pivota em ``data_julgamento`` — ``data_publicacao`` nao
    e dividida em janelas. O caminho normal valida o intervalo de
    publicacao via ``apply_input_pipeline_search(max_dias=366)``; o probe
    ``_cjsg_count_only`` precisa replicar para nao deixar passar janela
    > 366d silenciosamente para o backend.
    """
    scraper = jus.scraper("tjac", download_path=str(tmp_path))
    with pytest.raises(ValueError, match="366"):
        scraper.cjsg(
            "dano moral",
            data_publicacao_inicio="01/01/2020",
            data_publicacao_fim="01/01/2022",
            count_only=True,
        )
