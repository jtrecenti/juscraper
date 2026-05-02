"""Filter-propagation contract for TJRJ cjsg.

The TJRJ ASPX backend exposes only year-level granularity (``cmbAnoInicio``
/ ``cmbAnoFim``); ``data_julgamento_*`` and ``data_publicacao_*`` are
**not** accepted — :class:`InputCJSGTJRJ` rejects them via
``extra="forbid"`` (refs #93, #143). Code that previously relied on the
silent ``warn_unsupported`` behaviour now receives a :class:`TypeError`.
"""
import json

import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjrj.download import FORM_URL, RESULT_URL, build_cjsg_payload, extract_viewstate_fields
from tests._helpers import load_sample, urlencoded_body_subset_matcher


def _form_html() -> str:
    return load_sample("tjrj", "cjsg/post_initial.html")


def _xhr_no_results() -> dict:
    payload: dict = json.loads(load_sample("tjrj", "cjsg/xhr_no_results.json"))
    return payload


def _expected_body_subset(pesquisa: str, **overrides) -> dict:
    hidden = extract_viewstate_fields(_form_html())
    body = build_cjsg_payload(hidden=hidden, pesquisa=pesquisa, **overrides)
    body.pop("__VIEWSTATE", None)
    body.pop("__VIEWSTATEGENERATOR", None)
    body.pop("__EVENTVALIDATION", None)
    return body


def _add_form_get() -> None:
    responses.add(responses.GET, FORM_URL, body=_form_html(), status=200,
                  content_type="text/html; charset=utf-8")


def _add_form_post(pesquisa: str, **overrides) -> None:
    responses.add(
        responses.POST, FORM_URL, body=b"", status=200,
        match=[urlencoded_body_subset_matcher(_expected_body_subset(pesquisa, **overrides))],
    )


def _add_xhr_zero() -> None:
    responses.add(
        responses.POST, RESULT_URL,
        json=_xhr_no_results(), status=200,
        match=[json_params_matcher({"numPagina": 0, "pageSeq": "0"})],
    )


@responses.activate
def test_cjsg_all_filters_land_in_form_body(mocker):
    """Every TJRJ public filter must reach the ASPX form body."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post(
        "dano moral",
        ano_inicio="2023", ano_fim="2024",
        competencia="2", origem="1",
        tipo_acordao=False, tipo_monocratica=True,
        magistrado_codigo="123,456",
        orgao_codigo="789",
    )
    _add_xhr_zero()

    df = jus.scraper("tjrj").cjsg(
        "dano moral",
        paginas=1,
        ano_inicio=2023, ano_fim=2024,
        competencia="2", origem="1",
        tipo_acordao=False, tipo_monocratica=True,
        magistrado_codigo="123,456",
        orgao_codigo="789",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2024", ano_fim="2024")
    _add_xhr_zero()

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjrj").cjsg(
            pesquisa=None, query="dano moral",
            ano_inicio=2024, ano_fim=2024, paginas=1,
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2024", ano_fim="2024")
    _add_xhr_zero()

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjrj").cjsg(
            pesquisa=None, termo="dano moral",
            ano_inicio=2024, ano_fim=2024, paginas=1,
        )

    assert isinstance(df, pd.DataFrame)


def test_cjsg_data_julgamento_raises_typeerror():
    """``data_julgamento_*`` not accepted — TJRJ has only year granularity."""
    with pytest.raises(TypeError, match=r"data_julgamento_inicio"):
        jus.scraper("tjrj").cjsg(
            "dano moral", paginas=1,
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-03-31",
        )


def test_cjsg_data_publicacao_raises_typeerror():
    """``data_publicacao_*`` is also rejected — TJRJ does not expose it."""
    with pytest.raises(TypeError, match=r"data_publicacao_inicio"):
        jus.scraper("tjrj").cjsg(
            "dano moral", paginas=1,
            data_publicacao_inicio="2024-01-01",
            data_publicacao_fim="2024-03-31",
        )


def test_cjsg_data_inicio_alias_raises_typeerror():
    """``data_inicio``/``data_fim`` map to ``data_julgamento_*`` and TJRJ
    rejects that — caller still sees the deprecation warning before the
    ``TypeError`` from the schema."""
    with pytest.warns(DeprecationWarning) as warning_list:
        with pytest.raises(TypeError, match=r"data_julgamento_inicio"):
            jus.scraper("tjrj").cjsg(
                "dano moral", paginas=1,
                data_inicio="2024-01-01",
                data_fim="2024-03-31",
            )
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJRJ` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #93, #143)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjrj").cjsg("dano moral", paginas=1, kwarg_inventado="x")


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg`."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjrj").cjsg_download("dano moral", paginas=1, kwarg_inventado="x")
