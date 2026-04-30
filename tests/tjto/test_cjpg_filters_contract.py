"""Filter-propagation contract for TJTO cjpg (1st instance).

Same payload semantics as ``cjsg``, but the ``cjpg`` shortcut forces
``tip_criterio_inst='1'``.
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
        body=load_sample("tjto", "cjpg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[urlencoded_params_matcher(expected_payload, allow_blank=True)],
    )


@responses.activate
def test_cjpg_all_filters_land_in_body(mocker):
    """Every TJTO public filter must reach the form body for cjpg too."""
    mocker.patch("time.sleep")
    _add_post(build_cjsg_payload(
        '"dano moral"',
        start=0,
        type_minuta="3",
        tip_criterio_inst="1",
        tip_criterio_data="ASC",
        numero_processo="0000000-00.0000.0.00.0000",
        dat_jul_ini="2024-01-01",
        dat_jul_fim="2024-03-31",
        soementa=True,
    ))

    df = jus.scraper("tjto").cjpg(
        '"dano moral"',
        paginas=1,
        tipo_documento="sentencas",
        ordenacao="ASC",
        numero_processo="0000000-00.0000.0.00.0000",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        soementa=True,
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjpg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized to ``pesquisa``."""
    mocker.patch("time.sleep")
    _add_post(build_cjsg_payload('"dano moral"', start=0, tip_criterio_inst="1"))

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjto").cjpg(pesquisa=None, query='"dano moral"', paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjpg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized."""
    mocker.patch("time.sleep")
    _add_post(build_cjsg_payload('"dano moral"', start=0, tip_criterio_inst="1"))

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjto").cjpg(pesquisa=None, termo='"dano moral"', paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjpg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` map to ``data_julgamento_*`` via ``normalize_datas``."""
    mocker.patch("time.sleep")
    _add_post(build_cjsg_payload(
        '"dano moral"', start=0, tip_criterio_inst="1",
        dat_jul_ini="2024-01-01", dat_jul_fim="2024-03-31",
    ))

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjto").cjpg(
            '"dano moral"', paginas=1,
            data_inicio="2024-01-01", data_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
