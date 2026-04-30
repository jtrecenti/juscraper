"""Offline contract tests for TJTO cjpg (1st instance).

Same Solr backend as ``cjsg`` but ``tip_criterio_inst='1'``. The
``cjpg`` method does *not* invoke ``_fetch_ementa`` — only ``cjsg_ementa``
does — so this contract has no extra GET mocks.
"""
import pandas as pd
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjto.download import BASE_URL, build_cjsg_payload
from tests._helpers import load_sample

CJPG_FIELDS = {
    "processo", "uuid", "classe", "tipo_julgamento", "assunto",
    "competencia", "relator", "data_autuacao", "data_julgamento",
    "processo_link",
}


def _add_post(query: str, *, start: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjto", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[urlencoded_params_matcher(
            build_cjsg_payload(query, start=start, tip_criterio_inst="1"),
            allow_blank=True,
        )],
    )


@responses.activate
def test_cjpg_typical_com_paginacao(mocker):
    """Two pages: ``start=0`` then ``start=20`` (Solr offset)."""
    mocker.patch("time.sleep")
    _add_post('"dano moral"', start=0, sample_path="cjpg/results_normal_page_01.html")
    _add_post('"dano moral"', start=20, sample_path="cjpg/results_normal_page_02.html")

    df = jus.scraper("tjto").cjpg('"dano moral"', paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJPG_FIELDS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjpg_single_page(mocker):
    """Single-hit query: only one POST."""
    mocker.patch("time.sleep")
    _add_post('"despejo"', start=0, sample_path="cjpg/single_page.html")

    df = jus.scraper("tjto").cjpg('"despejo"', paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJPG_FIELDS <= set(df.columns)
    assert len(df) == 10


@responses.activate
def test_cjpg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame (not an error)."""
    mocker.patch("time.sleep")
    _add_post("juscraper_probe_zero_hits_xyzqwe", start=0,
              sample_path="cjpg/no_results.html")

    df = jus.scraper("tjto").cjpg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjpg_uses_instancia_1(mocker):
    """The cjpg shortcut must always send ``tip_criterio_inst='1'``."""
    mocker.patch("time.sleep")
    _add_post('"dano moral"', start=0, sample_path="cjpg/results_normal_page_01.html")

    jus.scraper("tjto").cjpg('"dano moral"', paginas=1)

    body = responses.calls[0].request.body or ""
    assert "tip_criterio_inst=1" in body
