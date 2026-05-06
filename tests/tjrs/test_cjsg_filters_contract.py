"""Filter-propagation contract for TJRS cjsg."""
import pandas as pd
import pytest
import responses

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises
from tests.tjrs.test_cjsg_contract import _add_page


@responses.activate
def test_cjsg_all_filters_land_in_form_body(mocker):
    """All TJRS public filters must reach the nested Solr params form body."""
    mocker.patch("time.sleep")
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        classe="Apelacao",
        assunto="Dano moral",
        orgao_julgador="Primeira Camara",
        relator="FULANO DE TAL",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
        tipo_processo="Civel",
        secao="crime",
    )

    df = jus.scraper("tjrs").cjsg(
        "dano moral",
        paginas=1,
        classe="Apelacao",
        assunto="Dano moral",
        orgao_julgador="Primeira Camara",
        relator="FULANO DE TAL",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
        tipo_processo="Civel",
        secao="crime",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body is built."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/no_results.json")

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjrs").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request body is built."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/no_results.json")

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjrs").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """Generic ``data_inicio``/``data_fim`` aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``
    and reach the Solr form body as the canonical ``data_julgamento_de/_ate``.
    """
    mocker.patch("time.sleep")
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjrs").cjsg(
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
    """Kwargs not declared in :class:`InputCJSGTJRS` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjrs").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )
