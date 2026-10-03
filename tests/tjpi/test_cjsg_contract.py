"""Offline contract tests for TJPI cjsg.

TJPI is a GET endpoint with query-string parameters. The page count is
read from the last-page link (``»``) of the ``ul.pagination`` paginator;
``single_page`` has no paginator at all, which is the 1-page path.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts.tjpi.download import BASE_URL, build_cjsg_params
from tests._helpers import load_sample

CJSG_MIN_COLUMNS = {"processo", "tipo", "classe", "assunto", "data_publicacao", "ementa"}


def _add_page(pesquisa: str, pagina: int, sample_path: str) -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params(pesquisa, page=pagina))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query exercises ``page=1`` and ``page=2`` query-string values."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.html")

    df = jus.scraper("tjpi").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single page scenario — sample has no pagination links; parser stops at 1."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca usucapiao extraordinario", 1, "cjsg/single_page.html")

    df = jus.scraper("tjpi").cjsg("mandado de seguranca usucapiao extraordinario", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_paginas_none_descobre_via_html(mocker):
    r"""``paginas=None`` exercises ``_get_total_pages`` against the HTML.

    The ``single_page`` sample has no ``ul.pagination``, so
    ``_get_total_pages`` returns 1. Only one request must hit the wire.
    """
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca usucapiao extraordinario", 1, "cjsg/single_page.html")

    df = jus.scraper("tjpi").cjsg(
        "mandado de seguranca usucapiao extraordinario", paginas=None,
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert len(responses.calls) == 1


@responses.activate
def test_cjsg_paginas_none_sem_link_de_ultima_pagina_levanta(mocker):
    """A paginator without the ``»`` link cannot tell the total: raise, never estimate.

    The largest visible ``page=N`` would be the end of the page window (2 here),
    so ``paginas=None`` would silently download fewer pages. The error comes
    after the first request and before any other.
    """
    mocker.patch("time.sleep")
    link_ultima = '<a class="page-link" href="/jurisprudences/search?page=5515&amp;q=dano+moral">&raquo;</a>'
    html = load_sample("tjpi", "cjsg/results_normal_page_01.html")
    assert html.count(link_ultima) == 2
    responses.add(
        responses.GET,
        BASE_URL,
        body=html.replace(link_ultima, ""),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params("dano moral", page=1))],
    )

    with pytest.raises(ValueError, match="última página"):
        jus.scraper("tjpi").cjsg("dano moral", paginas=None)

    assert len(responses.calls) == 1


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.html")

    df = jus.scraper("tjpi").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
