"""Filter-propagation contract for TJPR cjsg.

TJPR's ``cjsg`` exposes ``data_julgamento_inicio/fim`` and
``data_publicacao_inicio/fim``. Generic aliases ``data_inicio``/``data_fim``
ride ``normalize_datas`` to ``data_julgamento_*`` with a
``DeprecationWarning``. Search-term aliases are ``query`` and ``termo``.
"""
import pandas as pd
import pytest
import responses

import juscraper as jus
from tests._helpers import (
    assert_unknown_kwarg_raises,
    load_sample,
    query_param_subset_matcher,
    urlencoded_body_subset_matcher,
)
from tests.tjpr._helpers import SEARCH_URL, add_home


def _add_search(expected_body_subset: dict[str, str]):
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpr", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[
            query_param_subset_matcher({"actionType": "pesquisar"}),
            urlencoded_body_subset_matcher(expected_body_subset),
        ],
    )


@responses.activate
def test_cjsg_all_filters_land_in_body(mocker):
    """Every TJPR public filter must reach the form body."""
    mocker.patch("time.sleep")
    add_home()
    _add_search({
        "criterioPesquisa": "dano moral",
        "pageNumber": "1",
        "dataJulgamentoInicio": "01/01/2024",
        "dataJulgamentoFim": "31/03/2024",
        "dataPublicacaoInicio": "02/01/2024",
        "dataPublicacaoFim": "01/04/2024",
    })

    df = jus.scraper("tjpr").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        data_publicacao_inicio="02/01/2024",
        data_publicacao_fim="01/04/2024",
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias should normalize to ``pesquisa``."""
    mocker.patch("time.sleep")
    add_home()
    _add_search({"criterioPesquisa": "dano moral", "pageNumber": "1"})

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjpr").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias should normalize to ``pesquisa``."""
    mocker.patch("time.sleep")
    add_home()
    _add_search({"criterioPesquisa": "dano moral", "pageNumber": "1"})

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjpr").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` map to ``data_julgamento_*`` with a warning."""
    mocker.patch("time.sleep")
    add_home()
    _add_search({
        "criterioPesquisa": "dano moral",
        "pageNumber": "1",
        "dataJulgamentoInicio": "01/01/2024",
        "dataJulgamentoFim": "31/03/2024",
    })

    with pytest.warns(DeprecationWarning) as warnings_list:
        df = jus.scraper("tjpr").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="01/01/2024",
            data_fim="31/03/2024",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warnings_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJPR` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjpr").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjpr").cjsg_download,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


@responses.activate
def test_cjsg_download_query_alias_emits_deprecation_warning(mocker):
    """``cjsg_download`` direto consome ``query`` -> ``pesquisa`` via pipeline (refs #183).

    No TJPR ``cjsg`` resolve o alias antes de delegar (precisa do termo para
    o ``cjsg_parse``); este teste cobre o path lower-level direto, onde
    o pipeline em ``cjsg_download`` e quem consome o alias.
    """
    mocker.patch("time.sleep")
    add_home()
    _add_search({"criterioPesquisa": "dano moral", "pageNumber": "1"})

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        result = jus.scraper("tjpr").cjsg_download(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(result, list)


@responses.activate
def test_cjsg_download_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``cjsg_download`` direto: ``data_inicio`` -> ``data_julgamento_inicio`` no
    form body (refs #183)."""
    mocker.patch("time.sleep")
    add_home()
    _add_search({
        "criterioPesquisa": "dano moral",
        "pageNumber": "1",
        "dataJulgamentoInicio": "01/01/2024",
        "dataJulgamentoFim": "31/03/2024",
    })

    with pytest.warns(DeprecationWarning) as warning_list:
        result = jus.scraper("tjpr").cjsg_download(
            "dano moral",
            paginas=1,
            data_inicio="01/01/2024",
            data_fim="31/03/2024",
        )

    assert isinstance(result, list)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
