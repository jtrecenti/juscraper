"""Corpo HTTP 200 sem JSON não vira processo ausente nos dois agregadores PDPJ."""

import jwt
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.aggregators.pdpj.download import BASE_URL as PDPJ_BASE_URL
from juscraper.core.exceptions import InvalidJSONResponseError

CNJ = "10029886420194014100"
JUSBR_URL = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"


def _scraper(agregador):
    token = jwt.encode({"sub": "teste", "exp": 9999999999}, "segredo-de-teste-1234567890-1234567890", algorithm="HS256")
    scraper = jus.scraper(agregador, sleep_time=0)
    scraper.auth(token)
    return scraper


def _add_lista(agregador, corpo, content_type):
    if agregador == "jusbr":
        responses.add(
            responses.GET, JUSBR_URL, body=corpo, status=200, content_type=content_type,
            match=[query_param_matcher({"numeroProcesso": CNJ})],
        )
    else:
        responses.add(
            responses.GET, f"{PDPJ_BASE_URL}/processos/{CNJ}", body=corpo, status=200,
            content_type=content_type,
        )


@pytest.mark.parametrize(("agregador", "tentativas"), [("jusbr", 3), ("pdpj", 1)])
@pytest.mark.parametrize("corpo", ["", "<html>manutenção</html>"], ids=["vazio", "html"])
@responses.activate
def test_listagem_200_sem_json_preserva_linha_de_falha(agregador, tentativas, corpo, mocker):
    """Ambos classificam como JSON inválido; só o JusBR retenta o 200 transitório."""
    mocker.patch("time.sleep")
    scraper = _scraper(agregador)
    _add_lista(agregador, corpo, "text/html")

    with pytest.warns(UserWarning, match="json_invalido"):
        tabela = scraper.cpopg(CNJ)

    assert tabela["motivo_falha"].tolist() == ["json_invalido"]
    assert len(responses.calls) == tentativas


@responses.activate
def test_pdpj_existe_escalar_preserva_excecao_publica_em_200_vazio():
    """O caso escalar levanta ``InvalidJSONResponseError`` sem vazar JSONDecodeError."""
    scraper = _scraper("pdpj")
    responses.add(
        responses.GET, f"{PDPJ_BASE_URL}/processos/{CNJ}/existe", body="", status=200,
        content_type="application/json",
    )

    with pytest.raises(InvalidJSONResponseError):
        scraper.existe(CNJ)

    assert len(responses.calls) == 1


@pytest.mark.parametrize(("agregador", "corpo"), [("jusbr", '{"content": []}'), ("pdpj", "[]")])
@responses.activate
def test_lista_json_vazia_legitima_nao_vira_falha(agregador, corpo):
    """JSON com a forma de lista vazia do portal é diferente de corpo vazio."""
    scraper = _scraper(agregador)
    _add_lista(agregador, corpo, "application/json")

    tabela = scraper.cpopg(CNJ)

    assert tabela["motivo_falha"].tolist() == [None]
    assert len(responses.calls) == 1
