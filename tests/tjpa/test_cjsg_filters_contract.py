"""Filter-propagation contract for TJPA cjsg."""
import json

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
            query_type="anywords",
            query_scope="inteiroTeor",
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
        query_type="anywords",
        query_scope="inteiroTeor",
    )

    assert isinstance(df, pd.DataFrame)
    # O matcher deriva do builder; os nomes de campo do BFF ficam pinados aqui.
    assert json.loads(responses.calls[0].request.body) == {
        "query": "dano moral",
        "queryType": "anywords",
        "queryScope": "inteiroTeor",
        "origem": ["tribunal de justica"],
        "tipo": ["acordao"],
        "page": 0,
        "size": 25,
        "sortBy": "datapublicacao",
        "sortOrder": "asc",
        "relator": "FULANO DE TAL",
        "orgaoJulgadorColegiado": "1a Turma",
        "classe": "Apelacao",
        "assunto": "Dano moral",
        # O BFF devolve o julgado em D+1 para o filtro D: o julgamento vai um
        # dia antes do pedido, inclusive na virada de ano; publicacao, nao (#508).
        "dataJulgamentoInicio": "2023-12-31",
        "dataJulgamentoFim": "2024-03-30",
        "dataPublicacaoInicio": "2024-02-01",
        "dataPublicacaoFim": "2024-04-30",
    }


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
    the field and the public method name, although the pipeline runs in
    ``cjsg_download`` (refs #84, #93, #183, #263)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjpa").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
        rotulo="TJPAScraper.cjsg()",
    )


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjpa").cjsg_download,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


@responses.activate
def test_cjsg_datas_aceitam_formato_brasileiro(mocker):
    """Datas de julgamento e publicacao em ``DD/MM/YYYY`` chegam coercidas
    em ISO ao BFF.

    Cobre o caminho end-to-end de ``apply_input_pipeline_search`` lendo
    ``BACKEND_DATE_FORMAT='%Y-%m-%d'`` declarado em :class:`InputCJSGTJPA`
    e convertendo ambos os intervalos via ``coerce_brazilian_date``. Se o
    schema esquecer de declarar o ``BACKEND_DATE_FORMAT``, a data chega em
    ``DD/MM/YYYY`` ao ``build_cjsg_payload``, que nao a le como ISO, e o
    teste falha (refs #182, #173, #167)."""
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
            data_publicacao_inicio="2024-02-01",
            data_publicacao_fim="2024-04-30",
        ))],
    )

    df = jus.scraper("tjpa").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        data_publicacao_inicio="01/02/2024",
        data_publicacao_fim="30/04/2024",
    )

    assert isinstance(df, pd.DataFrame)
