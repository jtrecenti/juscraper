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
        data_publicacao_fim="2024-03-31T23:59:59",
        relator="Relator Teste",
        orgao_julgador="Camara Teste",
        tipo_processo="Cível",
        classe="Classe Teste",
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
        classe="Classe Teste",
        thesaurus=True,
    )

    assert isinstance(df, pd.DataFrame)


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@pytest.mark.parametrize(
    "filtro",
    [
        {"data_julgamento_inicio": "01/01/2024"},
        {"data_julgamento_fim": "31/03/2024"},
        {"data_julgamento_inicio": "01/01/2024", "data_julgamento_fim": "31/03/2024"},
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_filtros_sem_suporte_na_api_levantam_typeerror_sem_rede(metodo, filtro):
    """A API não filtra por data de julgamento: o schema a rejeita com
    ``TypeError`` antes de qualquer requisição."""
    nome = next(iter(filtro))
    with pytest.raises(TypeError, match=nome):
        getattr(jus.scraper("tjmt"), metodo)("dano moral", paginas=1, **filtro)

    assert len(responses.calls) == 0


@responses.activate(registry=OrderedRegistry)
def test_cjsg_classe_vai_como_fq_tipo_processo(mocker):
    """``classe`` chega à API em ``fqTipoProcesso``, a faceta de classe do
    portal, sem acento e em maiúsculas; o sample é a resposta real dessa
    busca, só com a classe pedida (#493)."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page(
        "dano moral",
        1,
        "cjsg/filtro_classe.json",
        tamanho_pagina=2,
        data_publicacao_inicio="2025-03-10",
        data_publicacao_fim="2025-03-10T23:59:59",
        classe="APELACAO CIVEL",
    )

    df = jus.scraper("tjmt").cjsg(
        "dano moral",
        paginas=1,
        tamanho_pagina=2,
        data_publicacao_inicio="2025-03-10",
        data_publicacao_fim="2025-03-10",
        classe="  Apelação   Cível ",
    )

    assert df["classe"].tolist() == ["APELAÇÃO CÍVEL", "APELAÇÃO CÍVEL"]


@pytest.mark.parametrize(
    ("classe", "enviado"),
    [
        (["Apelação Cível", " agravo  de instrumento "], "APELACAO CIVEL,AGRAVO DE INSTRUMENTO"),
        (("Apelação Cível", "", "Agravo de Instrumento"), "APELACAO CIVEL,AGRAVO DE INSTRUMENTO"),
        (["Apelação Cível"], "APELACAO CIVEL"),
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_lista_de_classes_vai_separada_por_virgula(mocker, classe, enviado):
    """A API soma as classes de ``fqTipoProcesso`` separadas por vírgula."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page("dano moral", 1, "cjsg/no_results.json", classe=enviado)

    jus.scraper("tjmt").cjsg("dano moral", paginas=1, classe=classe)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_classe_com_virgula_no_nome_chega_inteira_dentro_de_lista(mocker):
    """A vírgula de dentro do nome vai como U+FF0C: a API parte o valor na
    vírgula ASCII e, com ela, não casaria a classe. O sample é a resposta
    real dessa busca, só com a classe pedida."""
    mocker.patch("time.sleep")
    nome = "Exceção de Incompetência, Suspeição e Impedimento"
    _add_config()
    _add_page(
        "suspeição",
        1,
        "cjsg/filtro_classe_com_virgula.json",
        tamanho_pagina=2,
        classe="EXCECAO DE INCOMPETENCIA\uff0c SUSPEICAO E IMPEDIMENTO",
    )

    df = jus.scraper("tjmt").cjsg("suspeição", paginas=1, tamanho_pagina=2, classe=[nome])

    assert df["classe"].tolist() == [nome.upper()] * 2


@pytest.mark.parametrize(
    ("filtro", "valor", "mensagem"),
    [
        ("relator", "Fulano, Beltrano", "relator não aceita vírgula"),
        ("orgao_julgador", "Fulano, Beltrano", "orgao_julgador não aceita vírgula"),
        ("classe", "Apelação Cível, Agravo de Instrumento", "classe em texto não aceita vírgula"),
        ("classe", [], "lista sem nomes"),
    ],
)
@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@responses.activate(registry=OrderedRegistry)
def test_cjsg_filtros_de_nome_ambiguos_levantam_valueerror_sem_rede(metodo, filtro, valor, mensagem):
    """A API soma os nomes separados por vírgula: texto com vírgula filtraria
    por outros nomes ou devolveria busca vazia."""
    with pytest.raises(ValueError, match=mensagem):
        getattr(jus.scraper("tjmt"), metodo)("dano moral", paginas=1, **{filtro: valor})

    assert len(responses.calls) == 0


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
def test_cjsg_data_inicio_alias_aponta_para_julgamento_e_levanta_typeerror():
    """Os aliases genéricos de data apontam para data de julgamento: o usuário
    vê o ``DeprecationWarning`` do alias e depois o ``TypeError`` do schema,
    sem requisição."""
    with pytest.warns(DeprecationWarning) as warning_list, pytest.raises(
        TypeError, match="data_julgamento"
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
    assert len(responses.calls) == 0


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
    """O fim do intervalo de publicação chega como o último segundo do dia pedido."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        data_publicacao_inicio="2024-01-01",
        data_publicacao_fim="2024-03-31T23:59:59",
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
