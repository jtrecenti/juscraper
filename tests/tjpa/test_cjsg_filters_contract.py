"""Filter-propagation contract for TJPA cjsg."""
import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjpa.download import BASE_URL, build_cjsg_payload
from tests._helpers import assert_unknown_kwarg_raises, load_sample


@responses.activate
def test_cjsg_all_filters_land_in_json_body(mocker):
    """Every public filter must reach the BFF POST payload via ``build_cjsg_payload``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjpa", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            pagina_0based=0,
            relator="FULANO DE TAL",
            orgao_julgador_colegiado="1a Turma",
            classe="Apelacao",
            assunto="Dano moral",
            origem=["tribunal de justica"],
            tipo=["acordao"],
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-03-31",
            data_publicacao_inicio="2024-02-01",
            data_publicacao_fim="2024-04-30",
            sort_by="datapublicacao",
            sort_order="asc",
            query_type="any",
            query_scope="inteiroteor",
        ))],
    )

    df = jus.scraper("tjpa").cjsg(
        "dano moral",
        paginas=1,
        relator="FULANO DE TAL",
        orgao_julgador_colegiado="1a Turma",
        classe="Apelacao",
        assunto="Dano moral",
        origem=["tribunal de justica"],
        tipo=["acordao"],
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
        sort_by="datapublicacao",
        sort_order="asc",
        query_type="any",
        query_scope="inteiroteor",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjpa", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", pagina_0based=0))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjpa").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjpa", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", pagina_0based=0))],
    )

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjpa").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` generic aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``
    and reach the BFF body as ``dataJulgamentoInicio``/``dataJulgamentoFim``.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjpa", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            pagina_0based=0,
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-03-31",
        ))],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjpa").cjsg(
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
    """Kwargs not declared in :class:`InputCJSGTJPA` raise ``TypeError`` with
    the field name (refs #84, #93). Apos #183, ``cjsg`` e wrapper trivial e o
    pipeline roda em ``cjsg_download`` — entao o prefixo do erro reflete o
    ponto onde a validacao acontece.

    Nao migra para ``assert_unknown_kwarg_raises``: o helper asserta apenas
    o sufixo canonico, mas aqui o ponto e travar o ``method_label``
    (``TJPAScraper.cjsg_download``) — contrato mais forte que documenta
    onde a validacao acontece, nao so que ela acontece.
    """
    with pytest.raises(
        TypeError,
        match=r"TJPAScraper\.cjsg_download\(\) got unexpected keyword argument\(s\): 'kwarg_inventado'",
    ):
        jus.scraper("tjpa").cjsg("dano moral", paginas=1, kwarg_inventado="x")


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjpa").cjsg_download,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )
