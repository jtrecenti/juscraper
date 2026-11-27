"""Filter-propagation contract for TJRS cjsg."""
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
import pytest
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.courts.tjrs.schemas import InputCJSGTJRS
from tests._helpers import assert_unknown_kwarg_raises
from tests.tjrs.test_cjsg_contract import _add_page


@responses.activate
def test_cjsg_all_filters_land_in_form_body(mocker):
    """All TJRS public filters must reach the nested Solr params form body.

    Entrada ISO, datas em ``DD/MM/AAAA`` no body (#496).
    """
    mocker.patch("time.sleep")
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        classe="460",
        assunto="7780",
        orgao_julgador="65",
        relator="650",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        data_publicacao_inicio="01/02/2024",
        data_publicacao_fim="30/04/2024",
        tipo_processo="Civel",
        secao="crime",
    )

    df = jus.scraper("tjrs").cjsg(
        "dano moral",
        paginas=1,
        classe="460",
        assunto="7780",
        orgao_julgador="65",
        relator="650",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
        tipo_processo="Civel",
        secao="crime",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_aceita_date_e_datetime_nos_filtros_de_data(mocker):
    """``date`` e ``datetime`` chegam ao body no formato do backend, como a string equivalente."""
    mocker.patch("time.sleep")
    datas: dict[str, Any] = {
        "data_julgamento_inicio": date(2024, 1, 1),
        "data_julgamento_fim": datetime(2024, 3, 31, 15, 30, tzinfo=timezone.utc),
        "data_publicacao_inicio": date(2024, 2, 1),
        "data_publicacao_fim": datetime(2024, 4, 30, tzinfo=timezone.utc),
    }
    formato = InputCJSGTJRS.BACKEND_DATE_FORMAT
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        **{campo: valor.strftime(formato) for campo, valor in datas.items()},
    )

    df = jus.scraper("tjrs").cjsg("dano moral", paginas=1, **datas)

    assert isinstance(df, pd.DataFrame)


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@pytest.mark.parametrize(
    ("secao", "no_body"),
    [("CIVEL", "civel"), ("Cível", "civel"), (" crime ", "crime"), ("", None)],
)
@responses.activate
def test_cjsg_secao_ignora_caixa_e_acento_e_vazio_nao_filtra(mocker, metodo, secao, no_body):
    """``secao`` ignora caixa, acento e espaços nas pontas; ``""`` não filtra."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/no_results.json", secao=no_body)

    getattr(jus.scraper("tjrs"), metodo)("dano moral", paginas=1, secao=secao)

    assert len(responses.calls) == 1


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@pytest.mark.parametrize("secao", ["familia", "civil", "todas"])
@responses.activate
def test_cjsg_secao_fora_de_civel_e_crime_levanta(metodo, secao):
    """Seção desconhecida falha antes da busca, em vez de cobrir as duas em silêncio."""
    with pytest.raises(ValidationError, match="secao"):
        getattr(jus.scraper("tjrs"), metodo)("dano moral", paginas=1, secao=secao)

    assert not responses.calls


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@responses.activate
def test_cjsg_codigos_em_int_vao_ao_body_como_texto(mocker, metodo):
    """Os códigos vêm em ``int`` das colunas ``cod_*`` do cjsg; vão ao body como o texto equivalente."""
    mocker.patch("time.sleep")
    _add_page(
        "dano moral", 1, "cjsg/no_results.json", classe="460", assunto="7780", orgao_julgador="65", relator="650"
    )

    getattr(jus.scraper("tjrs"), metodo)(
        "dano moral", paginas=1, classe=460, assunto=7780, orgao_julgador=65, relator=" 650 "
    )

    assert len(responses.calls) == 1


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@pytest.mark.parametrize(
    ("filtro", "nome", "coluna"),
    [
        ("classe", "Recurso Inominado", "cod_classe_cnj"),
        ("assunto", "Indenização por Dano Material", "cod_assunto_cnj"),
        ("orgao_julgador", "Primeira Turma Recursal Cível", "cod_org_julg"),
        ("relator", "José Ricardo de Bem Sanhudo", "cod_relator"),
    ],
)
@responses.activate
def test_cjsg_filtro_por_nome_levanta_antes_da_busca(metodo, filtro, nome, coluna):
    """O portal monta ``cod_*:<valor>``: com nome, o Solr recusava a consulta e a busca voltava vazia sem erro."""
    with pytest.raises(ValidationError, match=coluna):
        getattr(jus.scraper("tjrs"), metodo)("dano moral", paginas=1, **{filtro: nome})

    assert not responses.calls


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
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
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
