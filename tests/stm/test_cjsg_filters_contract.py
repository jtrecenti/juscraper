"""Propagação de filtros do cjsg do STM para a query string."""
import datetime

import pytest
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.courts.stm.download import BASE_URL, montar_consulta_avancada
from tests._helpers import assert_unknown_kwarg_raises, load_sample


def _add_single_page() -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("stm", "cjsg/single_page.html"),
        content_type="text/html; charset=UTF-8",
    )


@responses.activate
def test_cjsg_todos_os_filtros_chegam_na_query(mocker):
    mocker.patch("time.sleep")
    _add_single_page()

    jus.scraper("stm").cjsg(
        "peculato OU furto",
        paginas=[3],
        campo="inteiro_teor",
        classe="APELAÇÃO",
        relator="CARLOS VUYK DE AQUINO",
        relator_acordao="ODILSON SAMPAIO BENZI",
        revisor="ARTUR VIDIGAL DE OLIVEIRA",
        assunto="PECULATO",
    )

    assert responses.calls[0].request.params == {
        "search_filter_option": "jurisprudencia",
        "search_filter": "inteiro_teor",
        "search_input": "peculato OU furto",
        "q": "peculato OU furto",
        "q_or": "peculato OU furto",
        "start": "200",
        "rows": "100",
        "fq_classe": "APELAÇÃO",
        "fq_ministro_relator": "CARLOS VUYK DE AQUINO",
        "fq_ministro_relator_acordao": "ODILSON SAMPAIO BENZI",
        "fq_ministro_revisor": "ARTUR VIDIGAL DE OLIVEIRA",
        "fq_assunto_pesquisa": "PECULATO",
    }


@responses.activate
def test_cjsg_sem_filtros_manda_so_a_busca(mocker):
    mocker.patch("time.sleep")
    _add_single_page()

    jus.scraper("stm").cjsg("deserção", paginas=1)

    assert responses.calls[0].request.params == {
        "search_filter_option": "jurisprudencia",
        "search_filter": "ementa",
        "search_input": "deserção",
        "q": "deserção",
        "q_or": "deserção",
        "start": "0",
        "rows": "100",
    }


@pytest.mark.parametrize("alias", ["query", "termo"])
@responses.activate
def test_cjsg_alias_deprecado_de_pesquisa(mocker, alias):
    mocker.patch("time.sleep")
    _add_single_page()

    with pytest.warns(DeprecationWarning, match=alias):
        df = jus.scraper("stm").cjsg(paginas=1, **{alias: "deserção"})

    assert responses.calls[0].request.params["q"] == "deserção"
    assert len(df) == 1


def test_cjsg_kwarg_desconhecido_levanta_type_error():
    assert_unknown_kwarg_raises(jus.scraper("stm").cjsg, "parametro_bobo", "deserção")


def _add_avancada() -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("stm", "cjsg/avancada_datas.html"),
        content_type="text/html; charset=UTF-8",
    )


JULGAMENTO = "(data_decisao:[2010-01-01T00:00:00.000Z TO 2022-06-08T23:59:59.000Z])"
PUBLICACAO = "(data_publicacao:[2021-10-01T00:00:00.000Z TO 2021-10-31T23:59:59.000Z])"


@responses.activate
def test_cjsg_intervalo_de_julgamento_sem_termo(mocker):
    """A busca do sample: pesquisa avançada só com o intervalo e um filtro da coluna lateral."""
    mocker.patch("time.sleep")
    _add_avancada()

    df = jus.scraper("stm").cjsg(
        "",
        data_julgamento_inicio="01/01/2010",
        data_julgamento_fim=datetime.date(2022, 6, 8),
        relator="CLAUDIO PORTUGAL DE VIVEIROS",
    )

    assert responses.calls[0].request.params == {
        "search_filter_option": "jurisprudencia",
        "search_filter": "busca_avancada",
        "q": JULGAMENTO,
        "q_or": "",  # vazio, como nos links de paginação do portal
        "start": "0",
        "rows": "100",
        "fq_ministro_relator": "CLAUDIO PORTUGAL DE VIVEIROS",
    }
    assert len(df) > 0
    assert set(df["relator"]) == {"CLAUDIO PORTUGAL DE VIVEIROS"}
    assert df["data_julgamento"].between(datetime.date(2010, 1, 1), datetime.date(2022, 6, 8)).all()


@pytest.mark.parametrize(
    ("pesquisa", "campo", "clausula"),
    [
        ("deserção", "ementa", '(ementa:"deserção")'),
        ('"corrupção ativa"', "ementa", '(ementa:"corrupção ativa")'),
        ('"deser*"', "ementa", '(ementa:"deser*")'),
        ("peculato", "inteiro_teor", '(inteiro_teor:"peculato")'),
        ("290", "referencia_legislativa", '(referencia_legislativa:"290")'),
        ("7000588-60.2021.7.00.0000", "numero", "(numero_processo:*70005886020217000000*)"),
    ],
)
@responses.activate
def test_cjsg_termo_e_intervalos_na_consulta_avancada(mocker, recwarn, pesquisa, campo, clausula):
    mocker.patch("time.sleep")
    _add_avancada()

    jus.scraper("stm").cjsg(
        pesquisa,
        campo=campo,
        data_julgamento_inicio="2010-01-01",
        data_julgamento_fim="2022-06-08",
        data_publicacao_inicio="01/10/2021",
        data_publicacao_fim="31/10/2021",
    )

    assert responses.calls[0].request.params["q"] == f"{clausula} AND {JULGAMENTO} AND {PUBLICACAO}"
    assert not recwarn.list


@pytest.mark.parametrize(
    ("pesquisa", "expressao"),
    [
        # Entre palavras sem operador vale o E, como na busca simples.
        ("corrupção ativa", '("corrupção" AND "ativa")'),
        ("corrupção E ativa", '("corrupção" AND "ativa")'),
        ("furto ou roubo", '("furto" OR "roubo")'),
        ('"furto" OU "roubo qualificado"', '("furto" OR "roubo qualificado")'),
        ("furto NÃO infração", '("furto" AND NOT "infração")'),
        ("detenção OU (código NÃO penal)", '("detenção" OR ("código" AND NOT "penal"))'),
        ("(furto roubo) OU peculato OU dano", '(("furto" AND "roubo") OR "peculato" OR "dano")'),
        ("deser*", "deser*"),
        ("em?argos deser*", "(em?argos AND deser*)"),
        ('"detenção civil"~2', '"detenção civil"~2'),
        # Palavra sem curinga vai entre aspas: o símbolo não vira sintaxe da consulta.
        ("9.099/95 habeas-corpus", '("9.099/95" AND "habeas-corpus")'),
        # Entre aspas, nada é sintaxe: nem o parêntese.
        ('"art. 9 ( inciso" OU furto', '("art. 9 ( inciso" OR "furto")'),
        # Entre aspas, o operador é palavra.
        ('acordo "não" previsto', '("acordo" AND "não" AND "previsto")'),
    ],
)
@responses.activate
def test_cjsg_operadores_traduzidos_para_a_consulta_avancada(mocker, recwarn, pesquisa, expressao):
    """Com data, os operadores da busca simples vão na sintaxe da pesquisa avançada."""
    mocker.patch("time.sleep")
    _add_avancada()

    jus.scraper("stm").cjsg(pesquisa, data_publicacao_inicio="01/10/2021", data_publicacao_fim="31/10/2021")

    assert responses.calls[0].request.params["q"] == f"(ementa:{expressao}) AND {PUBLICACAO}"
    assert not recwarn.list


@pytest.mark.parametrize(
    ("pesquisa", "campo", "erro"),
    [
        ("furto\\", "inteiro_teor", "barra invertida"),
        ('furto "roubo', "ementa", "aspas sem par"),
        ("(furto OU roubo", "ementa", "parênteses em pares"),
        ("furto) OU (roubo", "ementa", "parênteses em pares"),
        ("furto OU", "ementa", "um termo de cada lado"),
        ("E furto", "ementa", "um termo de cada lado"),
        ("furto NÃO", "ementa", "depois do NÃO"),
        ("()", "ementa", "dentro dos parênteses"),
        # Negação sem termo antes: a consulta avançada devolveria nada.
        ("NÃO furto", "ementa", "só aceita o NÃO depois de um termo"),
        ("furto OU NÃO roubo", "ementa", "só aceita o NÃO depois de um termo"),
        # E e OU no mesmo grupo: a precedência da consulta avançada não é a da leitura.
        ("furto roubo OU peculato", "ementa", "parênteses que digam a ordem"),
        ("(furto OU roubo E peculato) deserção", "ementa", "parênteses que digam a ordem"),
        ("9.099/9*", "ementa", "palavra com curinga"),
        ("7000588 OU 60", "numero", "só dígitos"),
        ("deserção", "tudo", "campo='tudo' não combina com filtro de data"),
    ],
)
def test_cjsg_termo_que_nao_cabe_na_consulta_avancada_levanta(pesquisa, campo, erro):
    with pytest.raises(ValueError, match=erro):
        jus.scraper("stm").cjsg(
            pesquisa, campo=campo, data_julgamento_inicio="01/01/2024", data_julgamento_fim="31/01/2024"
        )


@pytest.mark.parametrize("pesquisa", ["", "  ", '""', '" "'])
def test_consulta_avancada_sem_termo_fica_so_com_os_intervalos(pesquisa):
    datas = {"data_julgamento_inicio": "2010-01-01", "data_julgamento_fim": "2022-06-08"}

    assert montar_consulta_avancada(pesquisa, "ementa", datas) == JULGAMENTO


def test_consulta_avancada_lado_aberto_do_intervalo_vai_como_asterisco():
    """Como no formulário do portal; o método público preenche o lado que falta antes."""
    assert montar_consulta_avancada("", "ementa", {"data_julgamento_inicio": "2010-01-01"}) == (
        "(data_decisao:[2010-01-01T00:00:00.000Z TO *])"
    )
    assert montar_consulta_avancada("", "ementa", {"data_publicacao_fim": "2021-10-31"}) == (
        "(data_publicacao:[* TO 2021-10-31T23:59:59.000Z])"
    )


@responses.activate
def test_cjsg_intervalo_aberto_e_preenchido_com_aviso(mocker):
    mocker.patch("time.sleep")
    _add_avancada()

    with pytest.warns(UserWarning, match="data_julgamento_inicio"):
        jus.scraper("stm").cjsg("", data_julgamento_fim="08/06/2022")

    assert responses.calls[0].request.params["q"] == (
        "(data_decisao:[1990-01-01T00:00:00.000Z TO 2022-06-08T23:59:59.000Z])"
    )


def test_cjsg_inicio_depois_do_fim_levanta():
    with pytest.raises(ValueError, match="data_julgamento"):
        jus.scraper("stm").cjsg("", data_julgamento_inicio="02/01/2024", data_julgamento_fim="01/01/2024")


@responses.activate
def test_cjsg_alias_deprecado_de_data(mocker):
    mocker.patch("time.sleep")
    _add_avancada()

    with pytest.warns(DeprecationWarning, match="data_inicio"), pytest.warns(DeprecationWarning, match="data_fim"):
        jus.scraper("stm").cjsg("", data_inicio="01/01/2010", data_fim="08/06/2022")

    assert responses.calls[0].request.params["q"] == JULGAMENTO


def test_cjsg_campo_fora_do_dominio_levanta():
    with pytest.raises(ValidationError, match="campo"):
        jus.scraper("stm").cjsg("deserção", campo="notas")


@pytest.mark.parametrize("campo", ["referencia_legislativa", "tudo"])
@responses.activate
def test_cjsg_campo_vai_no_search_filter(mocker, campo):
    mocker.patch("time.sleep")
    _add_single_page()

    jus.scraper("stm").cjsg("290", paginas=1, campo=campo)

    assert responses.calls[0].request.params == {
        "search_filter_option": "jurisprudencia",
        "search_filter": campo,
        "search_input": "290",
        "q": "290",
        "q_or": "290",
        "start": "0",
        "rows": "100",
    }


@responses.activate
def test_cjsg_campo_tudo_sem_termo_aceita_filtro_de_data(mocker):
    """Sem termo, a consulta avançada só leva os intervalos, e o campo não entra nela."""
    mocker.patch("time.sleep")
    _add_avancada()

    jus.scraper("stm").cjsg("", campo="tudo", data_julgamento_inicio="01/01/2010", data_julgamento_fim="08/06/2022")

    assert responses.calls[0].request.params["q"] == JULGAMENTO
