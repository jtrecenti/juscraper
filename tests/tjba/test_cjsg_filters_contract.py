"""Filter-propagation contract for TJBA cjsg."""
from typing import Any

import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from tests._helpers import load_sample
from tests.tjba.test_cjsg_contract import BASE, _payload


@responses.activate
def test_cjsg_all_filters_land_in_graphql_body(mocker):
    """All TJBA public filters must reach the GraphQL variables payload."""
    mocker.patch("time.sleep")
    filters: dict[str, Any] = dict(
        numero_recurso="8000001-11.2024.8.05.0001",
        orgaos=[10, 20],
        relatores=[1],
        classes=[100],
        data_publicacao_inicio="2024-01-01",
        data_publicacao_fim="2024-03-31",
        segundo_grau=False,
        turmas_recursais=True,
        tipo_acordaos=False,
        tipo_decisoes_monocraticas=True,
        ordenado_por="relevancia",
        items_per_page=5,
    )
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjba", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 1, **filters))],
    )

    df = jus.scraper("tjba").cjsg("dano moral", paginas=[2], **filters)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before GraphQL variables are built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjba", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 0))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjba").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)
