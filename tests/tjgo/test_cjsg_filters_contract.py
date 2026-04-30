"""Filter-propagation contract for TJGO cjsg.

TJGO's backend filter is ``data_publicacao_*`` (canonical). The
``data_julgamento_*`` parameter is accepted by the public method but
emits ``warn_unsupported`` because the backend does not expose a
release-date filter — the body's ``DataInicial``/``DataFinal`` carry
publication dates only. The deprecated generic ``data_inicio``/``data_fim``
alias maps to ``data_julgamento_*`` via ``normalize_datas``, so it emits
both a ``DeprecationWarning`` and a ``UserWarning`` here.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjgo.download import SEARCH_URL, build_cjsg_payload
from tests._helpers import load_sample_bytes


def _add_get_prime() -> None:
    responses.add(responses.GET, SEARCH_URL, body=b"", status=200)


def _add_post(expected_body: dict) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample_bytes("tjgo", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(expected_body, allow_blank=True)],
    )


@responses.activate
def test_cjsg_all_filters_land_in_form_body(mocker):
    """Every TJGO public filter must reach the Projudi form body."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post(build_cjsg_payload(
        pesquisa="dano moral",
        page=1,
        id_instancia="2",
        id_area="1",
        id_serventia_subtipo="42",
        numero_processo="0000000-00.0000.0.00.0000",
        qtde_itens_pagina=20,
        data_publicacao_inicio="01/02/2024",
        data_publicacao_fim="30/04/2024",
    ))

    df = jus.scraper("tjgo").cjsg(
        "dano moral",
        paginas=1,
        id_instancia=2,
        id_area=1,
        id_serventia_subtipo=42,
        numero_processo="0000000-00.0000.0.00.0000",
        qtde_itens_pagina=20,
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post(build_cjsg_payload(pesquisa="dano moral", page=1))

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjgo").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post(build_cjsg_payload(pesquisa="dano moral", page=1))

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjgo").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_julgamento_emits_warn_unsupported(mocker):
    """``data_julgamento_*`` is not supported by TJGO; the client warns and drops it."""
    mocker.patch("time.sleep")
    _add_get_prime()
    # Body must NOT carry the date — backend filter is publicacao-only.
    _add_post(build_cjsg_payload(pesquisa="dano moral", page=1))

    with pytest.warns(UserWarning) as warning_list:
        df = jus.scraper("tjgo").cjsg(
            "dano moral",
            paginas=1,
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warning_list]
    assert any("data_julgamento_inicio" in m and "TJGO" in m for m in messages)
    assert any("data_julgamento_fim" in m and "TJGO" in m for m in messages)


@responses.activate
def test_cjsg_data_inicio_alias_emits_deprecation_and_unsupported(mocker):
    """Generic ``data_inicio``/``data_fim`` map to ``data_julgamento_*``,
    which TJGO emits ``warn_unsupported`` for. The body carries no date.
    """
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post(build_cjsg_payload(pesquisa="dano moral", page=1))

    with pytest.warns() as warning_list:
        df = jus.scraper("tjgo").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [(w.category, str(w.message)) for w in warning_list]
    assert any(c is DeprecationWarning and "data_inicio" in m for c, m in messages)
    assert any(c is DeprecationWarning and "data_fim" in m for c, m in messages)
    assert any(c is UserWarning and "data_julgamento" in m for c, m in messages)


@responses.activate
def test_cjsg_data_publicacao_canonico_no_extra_warning(mocker):
    """``data_publicacao_*`` is canonical for TJGO — no deprecation/unsupported."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post(build_cjsg_payload(
        pesquisa="dano moral", page=1,
        data_publicacao_inicio="01/01/2024",
        data_publicacao_fim="31/03/2024",
    ))

    df = jus.scraper("tjgo").cjsg(
        "dano moral",
        paginas=1,
        data_publicacao_inicio="2024-01-01",
        data_publicacao_fim="2024-03-31",
    )

    assert isinstance(df, pd.DataFrame)
