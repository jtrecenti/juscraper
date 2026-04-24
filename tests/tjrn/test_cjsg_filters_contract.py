"""Filter-propagation contract for TJRN cjsg."""
import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjrn.download import BASE_URL, build_cjsg_payload
from tests._helpers import load_sample


@responses.activate
def test_cjsg_all_filters_land_in_json_body(mocker):
    """Every public filter must reach the POST JSON payload via ``build_cjsg_payload``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            page=1,
            nr_processo="00000000000000000000",
            id_classe_judicial="123",
            id_orgao_julgador="456",
            id_relator="789",
            id_colegiado="10",
            dt_inicio="2024-01-01",
            dt_fim="2024-03-31",
            sistema="PJE",
            decisoes="Colegiadas",
            jurisdicoes="Tribunal de Justica",
            grau="2",
        ))],
    )

    df = jus.scraper("tjrn").cjsg(
        "dano moral",
        paginas=1,
        numero_processo="00000000000000000000",
        id_classe_judicial="123",
        id_orgao_julgador="456",
        id_relator="789",
        id_colegiado="10",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        sistema="PJE",
        decisoes="Colegiadas",
        jurisdicoes="Tribunal de Justica",
        grau="2",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjrn").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjrn").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_nr_processo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``nr_processo`` alias maps to ``numero_processo`` and
    lands in the payload as ``nr_processo``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral", page=1, nr_processo="00000000000000000000",
        ))],
    )

    with pytest.warns(DeprecationWarning, match="nr_processo.*numero_processo"):
        df = jus.scraper("tjrn").cjsg(
            "dano moral",
            paginas=1,
            nr_processo="00000000000000000000",
        )

    assert isinstance(df, pd.DataFrame)
