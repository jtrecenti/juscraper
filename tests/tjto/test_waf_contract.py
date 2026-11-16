"""Contratos offline do AWS WAF na frente da busca do TJTO.

Ao vivo (15/11/2026), o ``consulta.php`` respondeu 403 ao user agent
``juscraper/...`` e aceitou o de navegador por cerca de 7 buscas do mesmo IP.
Depois veio o desafio (HTTP 202 de corpo vazio, com
``x-amzn-waf-action: challenge``) e, mesmo com o cookie que um navegador obteve,
o CAPTCHA (HTTP 405, ``x-amzn-waf-action: captcha``). As respostas são
mockadas como chegaram: sem corpo, só com o cabeçalho. O bloqueio no meio de
uma paginação sobe como ``ColetaParcialError``, com as páginas já baixadas.
"""
import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError, ColetaParcialError
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


@pytest.mark.parametrize(
    ("metodo", "pasta"), [("cjsg", "cjsg"), ("cjsg_download", "cjsg"), ("cjpg", "cjpg"), ("cjpg_download", "cjpg")]
)
@responses.activate(registry=OrderedRegistry)
def test_bloqueio_no_meio_da_paginacao_guarda_as_paginas_baixadas(tjto, metodo, pasta):
    """O WAF desafia depois de algumas buscas: as páginas anteriores vêm lidas em ``.resultado``."""
    brutos = [load_sample("tjto", f"{pasta}/results_normal_page_0{pagina}.html") for pagina in (1, 2)]
    for bruto in brutos:
        responses.add(responses.POST, BASE_URL, body=bruto, content_type="text/html; charset=utf-8")
    responses.add(responses.POST, BASE_URL, body="", status=202, headers={"x-amzn-waf-action": "challenge"})

    falha = r"página 3 falhou.*faltam as páginas \[3, 4\].*depois de pelo menos 10 minutos"
    with pytest.raises(ColetaParcialError, match=falha) as erro:
        getattr(tjto, metodo)("dano moral", paginas=range(1, 5))

    pd.testing.assert_frame_equal(erro.value.resultado, tjto.cjsg_parse(brutos))
    assert isinstance(erro.value.__cause__, BotChallengeBlockedError)
    assert len(responses.calls) == 3


@responses.activate
def test_bloqueio_na_primeira_pagina_pedida_sobe_sem_parcial(tjto):
    responses.add(responses.POST, BASE_URL, body="", status=202, headers={"x-amzn-waf-action": "challenge"})

    with pytest.raises(BotChallengeBlockedError):
        tjto.cjsg("dano moral", paginas=[2, 3])

    assert len(responses.calls) == 1
