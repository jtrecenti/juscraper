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
    """Every public filter must reach the POST JSON payload via ``build_cjsg_payload``.

    ``data_julgamento_inicio``/``fim`` arrive in ISO at the public method but
    ``TJRNScraper`` rewrites them as ``DD-MM-YYYY`` (with dashes) before
    passing to ``cjsg_download_manager`` — the backend silently drops any
    other format. See ``_to_tjrn_date`` in ``courts/tjrn/client.py``.

    Note: ``TJRNScraper.cjsg`` exposes only ``data_julgamento_inicio``/``fim``;
    ``data_publicacao_*`` is not in the public signature, so the publication
    date filter does not enter the matcher.
    """
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
            dt_inicio="01-01-2024",
            dt_fim="31-03-2024",
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


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` generic aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``,
    are rewritten as ``DD-MM-YYYY`` by ``_to_tjrn_date`` (TJRN's backend
    silently ignores other formats) and reach the BFF payload as
    ``dt_inicio``/``dt_fim``.
    """
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
            dt_inicio="01-01-2024",
            dt_fim="31-03-2024",
        ))],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjrn").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJRN` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjrn").cjsg("dano moral", paginas=1, kwarg_inventado="x")


def test_cjsg_alias_conflict_raises():
    """Passar canonical e alias deprecado simultaneamente leva a ``ValueError``."""
    with pytest.raises(ValueError, match="numero_processo.*nr_processo"):
        jus.scraper("tjrn").cjsg(
            "dano moral", paginas=1,
            numero_processo="X", nr_processo="Y",
        )
