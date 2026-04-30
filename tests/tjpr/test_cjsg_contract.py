"""Offline contract tests for TJPR cjsg.

TJPR's flow:

1. ``GET /jurisprudencia/`` extracts ``JSESSIONID`` and the
   ``tjpr.url.crypto`` token (the scraper hits this endpoint twice
   per ``cjsg`` call — once during download, once during parse).
2. ``POST /jurisprudencia/publico/pesquisa.do?actionType=pesquisar``
   per page (``pageNumber``, 1-based, ``pageSize=10``).
3. For each row whose ementa is truncated with "Leia mais...", an
   extra ``GET ?actionType=exibirTextoCompleto&idProcesso=...`` is
   issued by ``cjsg_parse``.

The contract registers a single response for each kind of request;
``responses`` reuses registered responses across calls by default,
so the home GET (×2) and the ementa GETs (×N) all share one fixture.
"""
import pandas as pd
import responses

import juscraper as jus
from tests._helpers import load_sample, query_param_subset_matcher, urlencoded_body_subset_matcher

HOME_URL = "https://portal.tjpr.jus.br/jurisprudencia/"
SEARCH_URL = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do"

CJSG_MIN_COLUMNS = {"processo", "orgao_julgador", "relator", "data_julgamento", "ementa"}


def _add_home():
    responses.add(
        responses.GET,
        HOME_URL,
        body=load_sample("tjpr", "cjsg/home.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_search_page(pesquisa: str, pagina: int, sample_path: str):
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpr", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[
            query_param_subset_matcher({"actionType": "pesquisar"}),
            urlencoded_body_subset_matcher({
                "criterioPesquisa": pesquisa,
                "pageNumber": str(pagina),
            }),
        ],
    )


def _add_ementa_completa():
    """Single response shared by every ``actionType=exibirTextoCompleto`` GET.

    As of 2026-04 the upstream endpoint returns a generic Struts error page
    regardless of ``idProcesso``/``criterio``; we capture one and reuse it.
    """
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=load_sample("tjpr", "cjsg/ementa_completa.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[query_param_subset_matcher({"actionType": "exibirTextoCompleto"})],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query exercises ``pageNumber=1`` and ``pageNumber=2``."""
    mocker.patch("time.sleep")
    _add_home()
    _add_search_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    _add_search_page("dano moral", 2, "cjsg/results_normal_page_02.html")
    _add_ementa_completa()

    df = jus.scraper("tjpr").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single page scenario."""
    mocker.patch("time.sleep")
    _add_home()
    _add_search_page("direito civil", 1, "cjsg/single_page.html")
    _add_ementa_completa()

    df = jus.scraper("tjpr").cjsg("direito civil", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    _add_home()
    _add_search_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.html")

    df = jus.scraper("tjpr").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
