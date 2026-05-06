"""Filter-propagation contract for TJMT cjsg."""
import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises
from tests.tjmt.test_cjsg_contract import _add_config, _add_page


@responses.activate(registry=OrderedRegistry)
def test_cjsg_all_supported_filters_land_in_query_params(mocker):
    """Supported TJMT filters must reach the API query string."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page(
        "dano moral",
        1,
        "cjsg/filters_all.json",
        quantidade_por_pagina=5,
        tipo_consulta="Acordao",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        relator="306",
        orgao_julgador="30",
        tipo_processo="942",
        thesaurus=True,
    )

    df = jus.scraper("tjmt").cjsg(
        "dano moral",
        paginas=1,
        quantidade_por_pagina=5,
        tipo_consulta="Acordao",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        relator="306",
        orgao_julgador="30",
        tipo_processo="942",
        thesaurus=True,
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_classe_filter_documents_current_not_implemented_behavior(mocker):
    """The public ``classe`` parameter is accepted but currently unsupported by the API helper."""
    mocker.patch("time.sleep")
    _add_config()
    with pytest.raises(NotImplementedError, match="classe"):
        jus.scraper("tjmt").cjsg("dano moral", paginas=1, classe="Apelacao")


@responses.activate(registry=OrderedRegistry)
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request is built."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page("dano moral", 1, "cjsg/no_results.json")

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjmt").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request is built."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page("dano moral", 1, "cjsg/no_results.json")

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjmt").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """Generic ``data_inicio``/``data_fim`` aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``
    and reach the request as the canonical ``filtro.periodoData*`` query params.
    """
    mocker.patch("time.sleep")
    _add_config()
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjmt").cjsg(
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
    """Kwargs not declared in :class:`InputCJSGTJMT` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjmt").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


def test_cjsg_data_publicacao_raises_typeerror():
    """TJMT backend nao expoe filtro de data de publicacao — passar
    ``data_publicacao_*`` deve levantar ``TypeError`` em vez de silently drop
    (refs #165, #173, #186)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjmt").cjsg,
        "data_publicacao_inicio",
        "dano moral",
        paginas=1,
    )
