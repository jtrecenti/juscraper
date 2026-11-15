"""Contratos offline do AWS WAF na frente da busca do TJTO.

Ao vivo (15/11/2026), o ``consulta.php`` respondeu 403 ao user agent
``juscraper/...`` e aceitou o de navegador por cerca de 7 buscas do mesmo IP.
Depois veio o desafio (HTTP 202 de corpo vazio, com
``x-amzn-waf-action: challenge``) e, mesmo com o cookie que um navegador obteve,
o CAPTCHA (HTTP 405, ``x-amzn-waf-action: captcha``). As respostas são
mockadas como chegaram: sem corpo, só com o cabeçalho.
"""
import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.core.waf import USER_AGENT
from juscraper.courts.tjto.download import BASE_URL, EMENTA_URL
from tests._helpers import load_sample


@pytest.fixture
def tjto(mocker):
    mocker.patch("time.sleep")
    return jus.scraper("tjto")


def test_sessao_usa_o_user_agent_do_navegador():
    assert jus.scraper("tjto").session.headers["User-Agent"] == USER_AGENT


@responses.activate
def test_sem_bloqueio_a_busca_passa(tjto):
    responses.add(
        responses.POST, BASE_URL, body=load_sample("tjto", "cjsg/single_page.html"),
        content_type="text/html; charset=utf-8",
    )

    assert len(tjto.cjsg('"alimentos avoengos"', paginas=1)) == 9


@pytest.mark.parametrize(
    ("status", "cabecalhos"),
    [(202, {"x-amzn-waf-action": "challenge"}), (202, {}), (405, {"x-amzn-waf-action": "captcha"})],
    ids=["desafio", "desafio-sem-cabecalho", "captcha"],
)
@responses.activate
def test_bloqueio_do_waf_levanta_sem_repetir(tjto, status, cabecalhos):
    responses.add(responses.POST, BASE_URL, body="", status=status, headers=cabecalhos)

    with pytest.raises(BotChallengeBlockedError, match="Aguarde pelo menos 10 minutos"):
        tjto.cjsg("dano moral", paginas=1)

    assert len(responses.calls) == 1


@responses.activate
def test_desafio_no_get_da_ementa_levanta(tjto):
    responses.add(responses.GET, EMENTA_URL, body="", status=202, headers={"x-amzn-waf-action": "challenge"})

    with pytest.raises(BotChallengeBlockedError):
        tjto.cjsg_ementa("f4b3440350bb6c8e6bdd708d78c43e85")
