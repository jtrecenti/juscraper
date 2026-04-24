"""Filter-propagation contract for TJDFT cjsg."""
import warnings

import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from tests._helpers import load_sample
from tests.tjdft.test_cjsg_contract import BASE, _payload


@responses.activate
def test_cjsg_all_filters_land_in_json_body(mocker):
    """TJDFT-specific public filters must reach the POST JSON payload."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[
            json_params_matcher(
                _payload(
                    "dano moral",
                    1,
                    sinonimos=False,
                    espelho=False,
                    inteiro_teor=True,
                    quantidade_por_pagina=25,
                )
            )
        ],
    )

    df = jus.scraper("tjdft").cjsg(
        "dano moral",
        paginas=1,
        sinonimos=False,
        espelho=False,
        inteiro_teor=True,
        quantidade_por_pagina=25,
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 1))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjdft").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_emits_deprecation_warning(mocker):
    """Generic ``data_inicio``/``data_fim`` aliases emit deprecation warnings
    even though TJDFT ignores date filters (``warn_unsupported`` is the current
    behaviour). The request body stays identical to the no-filter baseline.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 1))],
    )

    # TJDFT also emits ``UserWarning`` via ``warn_unsupported`` because it
    # doesn't support date filters at all; ignore those so we can assert on
    # the DeprecationWarning from ``normalize_datas``.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = jus.scraper("tjdft").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    deprecation_messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("data_inicio" in m and "deprecado" in m for m in deprecation_messages)
    assert any("data_fim" in m and "deprecado" in m for m in deprecation_messages)
