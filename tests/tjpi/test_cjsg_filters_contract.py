"""Filter-propagation contract for TJPI cjsg.

TJPI has no date filter on the backend — the client doesn't call
``normalize_datas``. Therefore the alias tests cover only ``query`` and
``termo``. Passing ``data_inicio`` kwargs today would raise ``TypeError``
from the downstream request function, not a friendly warning.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts.tjpi.download import BASE_URL, build_cjsg_params
from tests._helpers import load_sample


@responses.activate
def test_cjsg_all_filters_land_in_query_params(mocker):
    """Every TJPI public filter must reach the GET query-string."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params(
            "dano moral",
            page=1,
            tipo="Acordao",
            relator="FULANO DE TAL",
            classe="Apelacao",
            orgao="1a Camara Civel",
        ))],
    )

    df = jus.scraper("tjpi").cjsg(
        "dano moral",
        paginas=1,
        tipo="Acordao",
        relator="FULANO DE TAL",
        classe="Apelacao",
        orgao="1a Camara Civel",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjpi").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjpi").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)
