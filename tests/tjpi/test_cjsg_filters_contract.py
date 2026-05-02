"""Filter-propagation contract for TJPI cjsg.

After PR #94, ``TJPIScraper.cjsg`` wires ``data_julgamento_inicio``/``fim``
through ``normalize_datas`` + ``to_iso_date`` + ``data_min``/``data_max``
on the GET query-string. Generic aliases ``data_inicio``/``data_fim`` ride
the same path with a ``DeprecationWarning``.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts.tjpi.download import BASE_URL, build_cjsg_params
from tests._helpers import assert_unsupported_date_filter_raises, load_sample


@responses.activate
def test_cjsg_all_filters_land_in_query_params(mocker):
    """Every TJPI public filter must reach the GET query-string.

    Note: ``TJPIScraper.cjsg`` exposes only ``data_julgamento_inicio``/``fim``
    (wired to ``data_min``/``data_max`` after ``to_iso_date``); ``data_publicacao_*``
    is not in the public signature, so the publication date filter does not
    enter the matcher.
    """
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
            data_min="2024-01-01",
            data_max="2024-03-31",
        ))],
    )

    df = jus.scraper("tjpi").cjsg(
        "dano moral",
        paginas=1,
        tipo="Acordao",
        relator="FULANO DE TAL",
        classe="Apelacao",
        orgao="1a Camara Civel",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
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


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_min(mocker):
    """``data_inicio``/``data_fim`` generic aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``,
    are converted to ISO by ``to_iso_date``, and reach the GET query-string
    as ``data_min``/``data_max``.
    """
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
            data_min="2024-01-01",
            data_max="2024-03-31",
        ))],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjpi").cjsg(
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
    """Kwargs not declared in :class:`InputCJSGTJPI` raise ``TypeError`` with
    the field name (refs #84, #93)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjpi").cjsg("dano moral", paginas=1, kwarg_inventado="x")


def test_cjsg_data_publicacao_kwarg_raises():
    """TJPI backend nao expoe filtro de data de publicacao; ``InputCJSGTJPI``
    nao herda ``DataPublicacaoMixin``, entao ``data_publicacao_*`` deve cair
    como ``extra_forbidden`` -> ``TypeError`` (refs #84, #93, #125, #186)."""
    assert_unsupported_date_filter_raises(
        jus.scraper("tjpi").cjsg,
        "data_publicacao_inicio",
        "dano moral",
        paginas=1,
    )


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjpi").cjsg_download("dano moral", paginas=1, kwarg_inventado="x")


@responses.activate
def test_cjsg_download_query_alias_emits_deprecation_warning(mocker):
    """``cjsg_download`` direto consome ``query`` -> ``pesquisa`` via pipeline (refs #183)."""
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
        result = jus.scraper("tjpi").cjsg_download(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(result, list)


@responses.activate
def test_cjsg_download_data_inicio_alias_maps_to_data_min(mocker):
    """``cjsg_download`` direto: ``data_inicio`` -> ``data_julgamento_inicio`` ->
    ``data_min`` na query-string (refs #183)."""
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
            data_min="2024-01-01",
            data_max="2024-03-31",
        ))],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        result = jus.scraper("tjpi").cjsg_download(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(result, list)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
