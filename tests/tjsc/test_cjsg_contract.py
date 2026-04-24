"""Offline contract tests for TJSC cjsg.

TJSC is dual-URL: page 1 hits ``listar_resultados``; page 2+ hit
``ajax_paginar_resultado``. The contract mocks each URL explicitly and
asserts the form body sent on each page.
"""
import pandas as pd
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjsc.download import AJAX_URL, SEARCH_URL, build_cjsg_form_body, cjsg_url_for_page
from tests._helpers import load_sample_bytes

# TJSC's AJAX page only exposes a subset of fields per hit (no ``classe`` or
# ``orgao_julgador`` rows), so minimum columns stays conservative.
CJSG_MIN_COLUMNS = {"processo", "relator", "data_julgamento", "data_publicacao", "ementa"}


def _add_page(pesquisa: str, pagina: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        cjsg_url_for_page(pagina),
        body=load_sample_bytes("tjsc", sample_path),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body(pesquisa, page=pagina), allow_blank=True
        )],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """First page hits ``SEARCH_URL``; second hits ``AJAX_URL``."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.html")

    df = jus.scraper("tjsc").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0
    # Confirm both URLs were hit — tests the dual-URL routing rule.
    hit_urls = {call.request.url for call in responses.calls}
    assert SEARCH_URL in hit_urls
    assert AJAX_URL in hit_urls


@responses.activate
def test_cjsg_single_page(mocker):
    """Single page scenario only hits ``SEARCH_URL``."""
    mocker.patch("time.sleep")
    _add_page("plano saude paciente doenca rara", 1, "cjsg/single_page.html")

    df = jus.scraper("tjsc").cjsg("plano saude paciente doenca rara", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0
    hit_urls = {call.request.url for call in responses.calls}
    assert hit_urls == {SEARCH_URL}


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.html")

    df = jus.scraper("tjsc").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
