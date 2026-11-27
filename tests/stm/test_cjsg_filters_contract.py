"""Propagação de filtros do cjsg do STM para a query string."""
import datetime

import pytest
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.courts.stm.download import BASE_URL, montar_consulta_avancada
from tests._helpers import assert_unknown_kwarg_raises, load_sample, params_enviados


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
        buscar_em="inteiro_teor",
        classe="APELAÇÃO",
        relator="CARLOS VUYK DE AQUINO",
        relator_acordao="ODILSON SAMPAIO BENZI",
        revisor="ARTUR VIDIGAL DE OLIVEIRA",
        assunto="PECULATO",
    )

    assert params_enviados(responses.calls[0].request) == {
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

    assert params_enviados(responses.calls[0].request) == {
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

    assert params_enviados(responses.calls[0].request)["q"] == "deserção"
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

    assert params_enviados(responses.calls[0].request) == {
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
    ("pesquisa", "buscar_em", "clausula"),
    [
        ("deserção", "ementa", '(ementa:"deserção")'),
        ('"corrupção ativa"', "ementa", '(ementa:"corrupção ativa")'),
        ('"deser*"', "ementa", '(ementa:"deser*")'),
        ("peculato", "inteiro_teor", '(inteiro_teor:"peculato")'),
        ("7000588-60.2021.7.00.0000", "numero", "(numero_processo:*70005886020217000000*)"),
    ],
)
@responses.activate
def test_cjsg_termo_e_intervalos_na_consulta_avancada(mocker, recwarn, pesquisa, buscar_em, clausula):
    mocker.patch("time.sleep")
    _add_avancada()

    jus.scraper("stm").cjsg(
        pesquisa,
        buscar_em=buscar_em,
        data_julgamento_inicio="2010-01-01",
        data_julgamento_fim="2022-06-08",
        data_publicacao_inicio="01/10/2021",
        data_publicacao_fim="31/10/2021",
    )

    assert params_enviados(responses.calls[0].request)["q"] == f"{clausula} AND {JULGAMENTO} AND {PUBLICACAO}"
    assert not recwarn.list


@pytest.mark.parametrize("pesquisa", ["corrupção ativa", "deser*", "furt?"])
@responses.activate
def test_cjsg_termo_com_operador_ou_curinga_sem_aspas_avisa_uma_vez(mocker, pesquisa):
    """Com data, o portal procura a expressão exata; a busca simples leria E ou curinga."""
    mocker.patch("time.sleep")
    _add_avancada()

    with pytest.warns(UserWarning, match="expressão exata") as avisos:
        jus.scraper("stm").cjsg(pesquisa, data_publicacao_inicio="01/10/2021", data_publicacao_fim="31/10/2021")

    assert len(avisos) == 1
    assert params_enviados(responses.calls[0].request)["q"] == f'(ementa:"{pesquisa}") AND {PUBLICACAO}'


@pytest.mark.parametrize(
    ("pesquisa", "buscar_em", "erro"),
    [
        ('"furto" OU "roubo"', "ementa", "aspas no meio"),
        ("furto\\", "inteiro_teor", "barra invertida"),
        ("7000588 OU 60", "numero", "só dígitos"),
    ],
)
def test_cjsg_termo_que_nao_cabe_na_consulta_avancada_levanta(pesquisa, buscar_em, erro):
    with pytest.raises(ValueError, match=erro):
        jus.scraper("stm").cjsg(
            pesquisa, buscar_em=buscar_em, data_julgamento_inicio="01/01/2024", data_julgamento_fim="31/01/2024"
        )


@pytest.mark.parametrize("pesquisa", ["", "  ", '""'])
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

    assert params_enviados(responses.calls[0].request)["q"] == (
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

    assert params_enviados(responses.calls[0].request)["q"] == JULGAMENTO


def test_cjsg_buscar_em_fora_do_dominio_levanta():
    with pytest.raises(ValidationError, match="buscar_em"):
        jus.scraper("stm").cjsg("deserção", buscar_em="tudo")


@pytest.mark.parametrize("valor", ["ementa", "inteiro_teor", "numero"])
@responses.activate
def test_cjsg_alias_campo_avisa_e_manda_o_mesmo_que_buscar_em(mocker, valor):
    """``campo``, nome antigo de ``buscar_em``, tem os mesmos valores e a mesma query."""
    mocker.patch("time.sleep")
    _add_single_page()
    _add_single_page()

    with pytest.warns(DeprecationWarning, match="'campo' está deprecado. Use 'buscar_em', com o mesmo valor"):
        jus.scraper("stm").cjsg("7000612", paginas=1, campo=valor)
    jus.scraper("stm").cjsg("7000612", paginas=1, buscar_em=valor)

    assert params_enviados(responses.calls[0].request) == params_enviados(responses.calls[1].request)
    assert params_enviados(responses.calls[0].request)["search_filter"] == valor


def test_cjsg_alias_campo_junto_com_buscar_em_levanta():
    with pytest.raises(ValueError, match="'buscar_em' e 'campo' ao mesmo tempo"):
        jus.scraper("stm").cjsg("deserção", campo="ementa", buscar_em="inteiro_teor")
