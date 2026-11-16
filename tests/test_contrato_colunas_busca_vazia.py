"""A busca sem resultados traz as mesmas colunas da busca com resultados.

Contrato comum do ``cjsg_parse`` sobre respostas reais gravadas: HTML (TJGO) e
JSON (TJRN, Elasticsearch, e TJPB, API própria). Antes, o DataFrame vazio vinha
sem nenhuma coluna, e ``df["processo"]`` levantava ``KeyError`` (#641). Cada
tribunal mantém as colunas que o parser dele entrega; nenhuma coluna herdada do
schema é imposta.
"""
import json

import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import RetryExhaustedError
from tests._helpers import load_sample


def _html(tribunal: str, caminho: str) -> list:
    # O Projudi do TJGO serve ISO-8859-1, como o download decodifica.
    return [load_sample(tribunal, caminho, encoding="iso-8859-1")]


def _json(tribunal: str, caminho: str) -> list:
    return [json.loads(load_sample(tribunal, caminho))]


CASOS = {
    "tjgo": (_html, "cjsg/results_normal_page_01.html", "cjsg/no_results.html"),
    "tjrn": (_json, "cjsg/results_normal_page_01.json", "cjsg/no_results.json"),
    "tjpb": (_json, "cjsg/results_normal_page_01.json", "cjsg/no_results.json"),
}


@pytest.mark.parametrize("tribunal", list(CASOS))
def test_busca_vazia_traz_as_colunas_da_busca_com_resultados(tribunal):
    carregar, com_resultados, sem_resultados = CASOS[tribunal]
    scraper = jus.scraper(tribunal)

    cheio = scraper.cjsg_parse(carregar(tribunal, com_resultados))
    vazio = scraper.cjsg_parse(carregar(tribunal, sem_resultados))

    assert not cheio.empty
    assert vazio.empty
    assert list(vazio.columns) == list(cheio.columns)
    assert list(scraper.cjsg_parse([]).columns) == list(cheio.columns)


@responses.activate
def test_bloqueio_nao_vira_busca_vazia_no_json(mocker):
    """O 403 do portal levanta erro em vez de virar DataFrame vazio com as colunas.

    No HTML do TJGO, a página do Turnstile vira vazio com aviso: ver
    ``tests/tjgo/test_cjsg_contract.py::test_cjsg_busca_vazia_avisa_do_turnstile``.
    """
    mocker.patch("time.sleep")
    responses.add(responses.POST, "https://jurisprudencia.tjrn.jus.br/api/pesquisar", status=403)

    with pytest.raises(RetryExhaustedError):
        jus.scraper("tjrn").cjsg("dano moral", paginas=1)
