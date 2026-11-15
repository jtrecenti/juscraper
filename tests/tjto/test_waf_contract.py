"""Contratos offline do AWS WAF na frente da busca do TJTO.

Ao vivo (15/11/2026), o ``consulta.php`` respondeu 403 ao user agent
``juscraper/...`` e ao do curl, e 200 ou o desafio (HTTP 202 de corpo vazio,
com ``x-amzn-waf-action: challenge``) ao user agent de navegador. O desafio é
mockado aqui como chegou: sem corpo, só com o cabeçalho.
"""
import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError, WafChallengeError
from juscraper.core.waf import USER_AGENT, WAF_COOKIE
from juscraper.courts.tjto.download import BASE_URL
from tests._helpers import load_sample


@pytest.fixture
def obter(mocker):
    return mocker.patch("juscraper.courts.tjto.client.obter_waf_token", return_value="token-novo")


@pytest.fixture
def tjto(mocker):
    mocker.patch("time.sleep")
    return jus.scraper("tjto")


def _desafio():
    responses.add(responses.POST, BASE_URL, body="", status=202, headers={"x-amzn-waf-action": "challenge"})


def _resultado():
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjto", "cjsg/single_page.html"),
        status=200,
        content_type="text/html; charset=utf-8",
    )


def test_sessao_usa_o_user_agent_do_navegador():
    assert jus.scraper("tjto").session.headers["User-Agent"] == USER_AGENT


@responses.activate
def test_sem_desafio_nao_chama_o_playwright(tjto, obter):
    _resultado()

    df = tjto.cjsg('"alimentos avoengos"', paginas=1)

    assert len(df) == 9
    obter.assert_not_called()


@responses.activate
def test_desafio_renova_o_cookie_e_repete_o_post(tjto, obter):
    _desafio()
    _resultado()

    df = tjto.cjsg('"alimentos avoengos"', paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 9
    obter.assert_called_once_with(BASE_URL, tribunal="TJTO")
    assert "Cookie" not in responses.calls[0].request.headers
    assert responses.calls[1].request.headers["Cookie"] == f"{WAF_COOKIE}=token-novo"
    assert responses.calls[0].request.body == responses.calls[1].request.body


@responses.activate
def test_desafio_repetido_depois_da_renovacao_levanta(tjto, obter):
    _desafio()
    _desafio()

    with pytest.raises(WafChallengeError, match="TJTO"):
        tjto.cjsg("dano moral", paginas=1)

    obter.assert_called_once()


@responses.activate
def test_falha_do_navegador_vira_waf_challenge_error(tjto, mocker):
    mocker.patch(
        "juscraper.courts.tjto.client.obter_waf_token",
        side_effect=RuntimeError("O portal do TJTO nao emitiu o cookie aws-waf-token em 60s."),
    )
    _desafio()

    with pytest.raises(WafChallengeError, match="nao emitiu o cookie"):
        tjto.cjsg("dano moral", paginas=1)


@responses.activate
def test_sem_playwright_o_erro_chega_ao_usuario(tjto, mocker):
    mocker.patch(
        "juscraper.courts.tjto.client.obter_waf_token",
        side_effect=ImportError("Instale com `pip install 'juscraper[waf]'`"),
    )
    _desafio()

    with pytest.raises(ImportError, match=r"juscraper\[waf\]"):
        tjto.cjsg("dano moral", paginas=1)


@responses.activate
def test_captcha_levanta_bloqueio_com_explicacao(tjto, obter):
    """Depois de várias buscas, o WAF passa a responder 405 com a página de CAPTCHA."""
    responses.add(
        responses.POST, BASE_URL, body="<title>Human Verification</title>", status=405,
        headers={"x-amzn-waf-action": "captcha"},
    )

    with pytest.raises(BotChallengeBlockedError, match="CAPTCHA"):
        tjto.cjsg("dano moral", paginas=1)

    obter.assert_not_called()
