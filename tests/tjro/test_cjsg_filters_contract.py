"""Filter-propagation contract for TJRO cjsg.

``relator`` and ``classe`` are the canonical kwargs in ``TJROScraper.cjsg``
(refs #129). The legacy ``magistrado`` / ``classe_judicial`` aliases are
still accepted and emit ``DeprecationWarning`` for one version. The
backend Elasticsearch payload keeps the original field names
(``ds_nome``, ``ds_classe_judicial``) — that is an internal detail of
the JURIS API and not exposed in the public signature.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjro.download import BASE_URL, build_cjsg_payload
from tests._helpers import assert_unsupported_date_filter_raises, load_sample


@responses.activate
def test_cjsg_all_filters_land_in_json_body(mocker):
    """Every public filter must reach the POST JSON payload via ``build_cjsg_payload``.

    Public filters are passed in canonical form (``relator``, ``classe``);
    the matcher asserts the backend body keeps ``ds_nome`` / ``ds_classe_judicial``.

    Note: ``TJROScraper.cjsg`` exposes only ``data_julgamento_inicio``/``fim``;
    ``data_publicacao_*`` is not in the public signature, so the publication
    date filter does not enter the matcher.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            offset=0,
            tipo=["ACORDAO"],
            nr_processo="00000000000000000000",
            relator="FULANO DE TAL",
            orgao_julgador=42,
            orgao_julgador_colegiado=7,
            classe="Apelacao",
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-03-31",
            instancia=[2],
            termo_exato=True,
        ))],
    )

    df = jus.scraper("tjro").cjsg(
        "dano moral",
        paginas=1,
        tipo=["ACORDAO"],
        numero_processo="00000000000000000000",
        relator="FULANO DE TAL",
        orgao_julgador=42,
        orgao_julgador_colegiado=7,
        classe="Apelacao",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        instancia=[2],
        termo_exato=True,
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", offset=0))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjro").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", offset=0))],
    )

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjro").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_nr_processo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``nr_processo`` alias maps to ``numero_processo`` and
    lands in the payload as ``nr_processo``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral", offset=0, nr_processo="00000000000000000000",
        ))],
    )

    with pytest.warns(DeprecationWarning, match="nr_processo.*numero_processo"):
        df = jus.scraper("tjro").cjsg(
            "dano moral",
            paginas=1,
            nr_processo="00000000000000000000",
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_magistrado_alias_emits_deprecation_warning(mocker):
    """The deprecated ``magistrado`` alias maps to ``relator`` and the
    backend body keeps the ``ds_nome`` field (refs #129)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral", offset=0, relator="FULANO DE TAL",
        ))],
    )

    with pytest.warns(DeprecationWarning, match="magistrado.*relator"):
        df = jus.scraper("tjro").cjsg(
            "dano moral",
            paginas=1,
            magistrado="FULANO DE TAL",
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_classe_judicial_alias_emits_deprecation_warning(mocker):
    """The deprecated ``classe_judicial`` alias maps to ``classe`` and the
    backend body keeps the ``ds_classe_judicial`` field (refs #129)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral", offset=0, classe="Apelacao",
        ))],
    )

    with pytest.warns(DeprecationWarning, match="classe_judicial.*classe"):
        df = jus.scraper("tjro").cjsg(
            "dano moral",
            paginas=1,
            classe_judicial="Apelacao",
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` generic aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``
    and reach the BFF payload as ``dtjulgamento_inicio``/``dtjulgamento_fim``.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            offset=0,
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-03-31",
        ))],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjro").cjsg(
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
    """Kwargs not declared in :class:`InputCJSGTJRO` raise ``TypeError`` with
    the field name (refs #84, #93)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjro").cjsg("dano moral", paginas=1, kwarg_inventado="x")


def test_cjsg_data_publicacao_raises_typeerror():
    """TJRO backend Elasticsearch nao expoe filtro de data de publicacao —
    ``InputCJSGTJRO`` herda apenas :class:`DataJulgamentoMixin`, entao
    ``data_publicacao_*`` deve cair como ``extra_forbidden`` -> ``TypeError``
    em vez de ser silently dropped (refs #186)."""
    assert_unsupported_date_filter_raises(
        jus.scraper("tjro").cjsg,
        "data_publicacao_inicio",
        "dano moral",
        paginas=1,
    )


def test_cjsg_unknown_kwarg_suggests_close_match():
    """Kwarg com typo ganha sugestao 'voce quis dizer X?' via difflib (refs #93)."""
    with pytest.raises(
        TypeError,
        match=r"'data_juglamento_inicio' \(você quis dizer 'data_julgamento_inicio'\?\)",
    ):
        jus.scraper("tjro").cjsg(
            "dano moral", paginas=1,
            data_juglamento_inicio="2024-01-01",
        )


def test_cjsg_alias_conflict_raises():
    """Passar canonical e alias deprecado simultaneamente leva a ``ValueError``."""
    with pytest.raises(ValueError, match="numero_processo.*nr_processo"):
        jus.scraper("tjro").cjsg(
            "dano moral", paginas=1,
            numero_processo="X", nr_processo="Y",
        )


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjro").cjsg_download("dano moral", paginas=1, kwarg_inventado="x")


@responses.activate
def test_cjsg_download_query_alias_emits_deprecation_warning(mocker):
    """``cjsg_download`` direto consome ``query`` -> ``pesquisa`` via pipeline (refs #183)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", offset=0))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        result = jus.scraper("tjro").cjsg_download(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(result, list)


@responses.activate
def test_cjsg_download_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``cjsg_download`` direto: ``data_inicio`` -> ``data_julgamento_inicio`` no
    payload (refs #183)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            offset=0,
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-03-31",
        ))],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        result = jus.scraper("tjro").cjsg_download(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(result, list)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
