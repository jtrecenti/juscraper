"""Filter-propagation contract for TJSC cjsg."""
import pandas as pd
import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjsc.download import build_cjsg_form_body, cjsg_url_for_page
from tests._helpers import load_sample_bytes


@responses.activate
def test_cjsg_all_filters_land_in_form_body(mocker):
    """Every TJSC public filter must reach the eproc form body."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        cjsg_url_for_page(1),
        body=load_sample_bytes("tjsc", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body(
                "dano moral",
                page=1,
                campo="I",
                processo="00000000000000000000",
                dt_decisao_inicio="2024-01-01",
                dt_decisao_fim="2024-03-31",
                dt_publicacao_inicio="2024-02-01",
                dt_publicacao_fim="2024-04-30",
            ),
            allow_blank=True,
        )],
    )

    df = jus.scraper("tjsc").cjsg(
        "dano moral",
        paginas=1,
        campo="I",
        processo="00000000000000000000",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        cjsg_url_for_page(1),
        body=load_sample_bytes("tjsc", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body("dano moral", page=1), allow_blank=True,
        )],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjsc").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        cjsg_url_for_page(1),
        body=load_sample_bytes("tjsc", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body("dano moral", page=1), allow_blank=True,
        )],
    )

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjsc").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_dt_decisao(mocker):
    """``data_inicio``/``data_fim`` generic aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``
    and reach the form body as ``dtDecisaoInicio``/``dtDecisaoFim``.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        cjsg_url_for_page(1),
        body=load_sample_bytes("tjsc", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body(
                "dano moral",
                page=1,
                dt_decisao_inicio="2024-01-01",
                dt_decisao_fim="2024-03-31",
            ),
            allow_blank=True,
        )],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjsc").cjsg(
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
    """Kwargs not declared in :class:`InputCJSGTJSC` raise ``TypeError`` with
    the field name (refs #84, #93)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjsc").cjsg("dano moral", paginas=1, kwarg_inventado="x")


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjsc").cjsg_download("dano moral", paginas=1, kwarg_inventado="x")


@responses.activate
def test_cjsg_download_query_alias_emits_deprecation_warning(mocker):
    """``cjsg_download`` direto consome ``query`` -> ``pesquisa`` via pipeline (refs #183)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        cjsg_url_for_page(1),
        body=load_sample_bytes("tjsc", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body("dano moral", page=1), allow_blank=True,
        )],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        result = jus.scraper("tjsc").cjsg_download(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(result, list)


@responses.activate
def test_cjsg_download_data_inicio_alias_maps_to_dt_decisao(mocker):
    """``cjsg_download`` direto: ``data_inicio`` -> ``data_julgamento_inicio`` ->
    ``dtDecisaoInicio`` no form body (refs #183)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        cjsg_url_for_page(1),
        body=load_sample_bytes("tjsc", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body(
                "dano moral",
                page=1,
                dt_decisao_inicio="2024-01-01",
                dt_decisao_fim="2024-03-31",
            ),
            allow_blank=True,
        )],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        result = jus.scraper("tjsc").cjsg_download(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(result, list)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
