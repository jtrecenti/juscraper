"""Filter-propagation contract for TJDFT cjsg."""
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
