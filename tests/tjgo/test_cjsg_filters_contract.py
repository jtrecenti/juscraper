"""Filter-propagation contract for TJGO cjsg.

TJGO's backend filter is ``data_publicacao_*`` (canonical). The
``data_julgamento_*`` parameter is **not** accepted: the Projudi backend
does not expose a release-date filter and the schema
:class:`InputCJSGTJGO` rejects it via ``extra="forbid"`` (refs #93,
#165). Code that previously relied on the silent ``warn_unsupported``
behaviour now receives a :class:`TypeError`.
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


def test_cjsg_data_julgamento_raises_typeerror():
    """``data_julgamento_*`` is not supported by TJGO; the schema rejects it.

    Was previously ``warn_unsupported`` (silent drop) — switched to ``TypeError``
    in refs #93/#165 so callers cannot accidentally believe the filter was
    applied.
    """
    with pytest.raises(TypeError, match=r"data_julgamento_inicio"):
        jus.scraper("tjgo").cjsg(
            "dano moral",
            paginas=1,
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-03-31",
        )


def test_cjsg_data_inicio_alias_raises_typeerror():
    """``data_inicio``/``data_fim`` map to ``data_julgamento_*`` and TJGO
    rejects that — caller still sees the deprecation warning before the
    ``TypeError`` from the schema."""
    with pytest.warns(DeprecationWarning) as warning_list:
        with pytest.raises(TypeError, match=r"data_julgamento_inicio"):
            jus.scraper("tjgo").cjsg(
                "dano moral",
                paginas=1,
                data_inicio="2024-01-01",
                data_fim="2024-03-31",
            )
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJGO` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjgo").cjsg("dano moral", paginas=1, kwarg_inventado="x")


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjgo").cjsg_download("dano moral", paginas=1, kwarg_inventado="x")


def test_cjsg_download_data_julgamento_raises_typeerror():
    """``cjsg_download`` tambem rejeita ``data_julgamento_*`` — TJGO Projudi nao
    expoe esse filtro, e o pipeline em ``cjsg_download`` agora pega o caso
    direto (antes do #183 era silenciosamente dropado pelo trio
    normalize_pesquisa/_paginas/_datas)."""
    with pytest.raises(TypeError, match=r"data_julgamento_inicio"):
        jus.scraper("tjgo").cjsg_download(
            "dano moral",
            paginas=1,
            data_julgamento_inicio="2024-01-01",
        )


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
