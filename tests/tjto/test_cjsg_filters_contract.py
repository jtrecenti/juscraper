"""Filter-propagation contract for TJTO cjsg.

The Solr backend uses ``tempo_julgados='pers'`` (custom interval) when
``dat_jul_ini``/``dat_jul_fim`` are populated; ``to_br_date`` converts ISO
``yyyy-mm-dd`` into ``dd/mm/yyyy``. The matchers here mirror that flow.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjto.download import BASE_URL, build_cjsg_payload
from tests._helpers import load_sample


def _add_post(expected_payload: dict) -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjto", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[urlencoded_params_matcher(expected_payload, allow_blank=True)],
    )


@responses.activate
def test_cjsg_all_filters_land_in_body(mocker):
    """Every TJTO public filter must reach the form body."""
    mocker.patch("time.sleep")
    _add_post(build_cjsg_payload(
        "dano moral",
        start=0,
        type_minuta="2",
        tip_criterio_inst="2",
        tip_criterio_data="ASC",
        numero_processo="0000000-00.0000.0.00.0000",
        dat_jul_ini="2024-01-01",
        dat_jul_fim="2024-03-31",
        soementa=True,
    ))

    df = jus.scraper("tjto").cjsg(
        "dano moral",
        paginas=1,
        tipo_documento="decisoes",
        ordenacao="ASC",
        numero_processo="0000000-00.0000.0.00.0000",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        soementa=True,
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized to ``pesquisa``."""
    mocker.patch("time.sleep")
    _add_post(build_cjsg_payload("dano moral", start=0, tip_criterio_inst="2"))

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjto").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized."""
    mocker.patch("time.sleep")
    _add_post(build_cjsg_payload("dano moral", start=0, tip_criterio_inst="2"))

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjto").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` map to ``data_julgamento_*`` via ``normalize_datas``."""
    mocker.patch("time.sleep")
    _add_post(build_cjsg_payload(
        "dano moral", start=0, tip_criterio_inst="2",
        dat_jul_ini="2024-01-01", dat_jul_fim="2024-03-31",
    ))

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjto").cjsg(
            "dano moral", paginas=1,
            data_inicio="2024-01-01", data_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJTO` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjto").cjsg("dano moral", paginas=1, kwarg_inventado="x")


def test_cjpg_unknown_kwarg_raises():
    """Same as ``test_cjsg_unknown_kwarg_raises`` for the cjpg endpoint
    (validates :class:`InputCJPGTJTO`)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjto").cjpg("dano moral", paginas=1, kwarg_inventado="x")
