"""Propagação de filtros do cjsg do STM para a query string."""
import pytest
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.courts.stm.download import BASE_URL
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


@pytest.mark.parametrize(
    "kwarg",
    [
        "parametro_bobo",
        "data_julgamento_inicio",
        "data_julgamento_fim",
        "data_publicacao_inicio",
        "data_publicacao_fim",
    ],
)
def test_cjsg_kwarg_desconhecido_levanta_type_error(kwarg):
    assert_unknown_kwarg_raises(jus.scraper("stm").cjsg, kwarg, "deserção", valor="01/01/2024")


def test_cjsg_campo_fora_do_dominio_levanta():
    with pytest.raises(ValidationError, match="campo"):
        jus.scraper("stm").cjsg("deserção", campo="tudo")
