"""Filter-propagation contract for TJPB cjsg.

The TJPB backend's release-date filter is ``dt_inicio``/``dt_fim`` inside
``jurisprudencia``; ``normalize_datas`` keeps ISO ``yyyy-mm-dd`` so the
matchers compare against ISO strings. The client also runs a post-filter
on the parsed DataFrame against ``data_julgamento`` — for filter contracts
we use the ``no_results`` sample so the post-filter is a no-op regardless
of date ranges.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjpb.download import BASE_URL, SEARCH_URL, TOKEN_RE, build_cjsg_payload
from tests._helpers import load_sample, load_sample_bytes

_HOME_HTML_BYTES = load_sample_bytes("tjpb", "cjsg/home.html")
_TOKEN_MATCH = TOKEN_RE.search(_HOME_HTML_BYTES.decode("utf-8"))
assert _TOKEN_MATCH is not None, "captured TJPB home.html lacks <meta name='_token' ...>"
_TOKEN = _TOKEN_MATCH.group(1)


def _add_get_home() -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=_HOME_HTML_BYTES,
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_post_no_results(expected_payload: dict) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpb", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(expected_payload)],
    )


@responses.activate
def test_cjsg_all_filters_land_in_body(mocker):
    """Every TJPB public filter must reach the JSON body."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post_no_results(build_cjsg_payload(
        token=_TOKEN,
        pesquisa="dano moral",
        page=1,
        nr_processo="0000000-00.0000.0.00.0000",
        id_classe_judicial="C123",
        id_orgao_julgador="O456",
        id_relator="R789",
        id_origem="2",
        dt_inicio="2024-01-01",
        dt_fim="2024-03-31",
        decisoes=True,
    ))

    df = jus.scraper("tjpb").cjsg(
        "dano moral",
        paginas=1,
        numero_processo="0000000-00.0000.0.00.0000",
        id_classe_judicial="C123",
        id_orgao_julgador="O456",
        id_relator="R789",
        id_origem="2",
        decisoes=True,
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized to ``pesquisa``."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post_no_results(build_cjsg_payload(token=_TOKEN, pesquisa="dano moral", page=1))

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjpb").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post_no_results(build_cjsg_payload(token=_TOKEN, pesquisa="dano moral", page=1))

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjpb").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_nr_processo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``nr_processo`` alias maps to ``numero_processo``."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post_no_results(build_cjsg_payload(
        token=_TOKEN, pesquisa="dano moral", page=1,
        nr_processo="0000000-00.0000.0.00.0000",
    ))

    with pytest.warns(DeprecationWarning, match="nr_processo.*deprecado"):
        df = jus.scraper("tjpb").cjsg(
            "dano moral", paginas=1,
            nr_processo="0000000-00.0000.0.00.0000",
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` map to ``data_julgamento_*`` via ``normalize_datas``."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post_no_results(build_cjsg_payload(
        token=_TOKEN, pesquisa="dano moral", page=1,
        dt_inicio="2024-01-01", dt_fim="2024-03-31",
    ))

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjpb").cjsg(
            "dano moral", paginas=1,
            data_inicio="2024-01-01", data_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
