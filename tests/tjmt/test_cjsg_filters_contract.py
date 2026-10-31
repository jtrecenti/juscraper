"""Contrato de propagação de filtros do cjsg do TJMT."""
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
        "cjsg/no_results.json",
        tamanho_pagina=5,
        tipo_consulta="Acordao",
        data_publicacao_inicio="2024-01-01",
        data_publicacao_fim="2024-04-01",
        relator="Relator Teste",
        orgao_julgador="Camara Teste",
        tipo_processo="Cível",
        thesaurus=True,
    )

    df = jus.scraper("tjmt").cjsg(
        "dano moral",
        paginas=1,
        tamanho_pagina=5,
        tipo_consulta="Acordao",
        data_publicacao_inicio="2024-01-01",
        data_publicacao_fim="2024-03-31",
        relator="Relator Teste",
        orgao_julgador="Camara Teste",
        tipo_processo="Cível",
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
def test_cjsg_data_inicio_alias_preserves_unsupported_judgment_filter():
    """Aliases de data genéricos continuam apontando para data de julgamento."""
    with pytest.warns(DeprecationWarning) as warning_list, pytest.raises(
        NotImplementedError, match="data_julgamento"
    ):
        jus.scraper("tjmt").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

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


@responses.activate(registry=OrderedRegistry)
def test_cjsg_data_publicacao_eh_suportada(mocker):
    """Datas de publicação chegam ao endpoint novo com limite final exclusivo."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        data_publicacao_inicio="2024-01-01",
        data_publicacao_fim="2024-04-01",
    )

    dataframe = jus.scraper("tjmt").cjsg(
        "dano moral",
        paginas=1,
        data_publicacao_inicio="2024-01-01",
        data_publicacao_fim="2024-03-31",
    )

    assert isinstance(dataframe, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_quantidade_por_pagina_alias_emits_deprecation_warning(mocker):
    """``quantidade_por_pagina`` e alias deprecado de ``tamanho_pagina`` (refs #211)."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page("dano moral", 1, "cjsg/no_results.json", tamanho_pagina=5)

    with pytest.warns(DeprecationWarning, match="quantidade_por_pagina.*deprecado"):
        df = jus.scraper("tjmt").cjsg(
            "dano moral", paginas=1, quantidade_por_pagina=5
        )

    assert isinstance(df, pd.DataFrame)


def test_cjsg_tamanho_pagina_collision_raises():
    """Passar canonico + alias simultaneamente levanta ValueError (refs #211)."""
    with pytest.raises(ValueError, match=r"tamanho_pagina.*quantidade_por_pagina"):
        jus.scraper("tjmt").cjsg(
            "dano moral", paginas=1, tamanho_pagina=5, quantidade_por_pagina=10
        )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_data_julgamento_continua_indisponivel():
    """A API nova não oferece filtro por data de julgamento."""
    with pytest.raises(NotImplementedError, match="data_julgamento"):
        jus.scraper("tjmt").cjsg(
            "dano moral",
            paginas=1,
            data_julgamento_inicio="01/01/2024",
            data_julgamento_fim="31/03/2024",
        )
