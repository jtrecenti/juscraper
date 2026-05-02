"""Filter-propagation contract for TJBA cjsg."""
from typing import Any

import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from tests._helpers import assert_unsupported_date_filter_raises, load_sample
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
        tamanho_pagina=5,
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


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJBA` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjba").cjsg("dano moral", paginas=1, kwarg_inventado="x")


@responses.activate
def test_cjsg_items_per_page_alias_emits_deprecation_warning(mocker):
    """``items_per_page`` e alias deprecado de ``tamanho_pagina`` (refs #211)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjba", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 0, tamanho_pagina=5))],
    )

    with pytest.warns(DeprecationWarning, match="items_per_page.*deprecado"):
        df = jus.scraper("tjba").cjsg("dano moral", paginas=1, items_per_page=5)

    assert isinstance(df, pd.DataFrame)


def test_cjsg_tamanho_pagina_collision_raises():
    """Passar canonico + alias simultaneamente levanta ValueError (refs #211)."""
    with pytest.raises(ValueError, match=r"tamanho_pagina.*items_per_page"):
        jus.scraper("tjba").cjsg(
            "dano moral", paginas=1, tamanho_pagina=5, items_per_page=10
        )


def test_cjsg_data_julgamento_raises_typeerror():
    """TJBA backend GraphQL so expoe filtro de data de publicacao —
    ``InputCJSGTJBA`` herda apenas :class:`DataPublicacaoMixin`, entao
    ``data_julgamento_*`` deve cair como ``extra_forbidden`` -> ``TypeError``
    em vez de ser silently dropped (refs #186)."""
    assert_unsupported_date_filter_raises(
        jus.scraper("tjba").cjsg,
        "data_julgamento_inicio",
        "dano moral",
        paginas=1,
    )
