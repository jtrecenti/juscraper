"""Mensagem de ``BotChallengeBlockedError`` e das subclasses que descrevem outro sintoma."""
from __future__ import annotations

from juscraper.core.exceptions import BotChallengeBlockedError, WafChallengeError
from juscraper.courts.trf6.download import DesafioF5Error

URL = "https://example.test/consulta"


def test_mensagem_padrao_descreve_o_403():
    erro = BotChallengeBlockedError("TRF3", URL, reference="18.abc")
    assert erro.args == (
        f"TRF3 bloqueou a requisição (HTTP 403) em {URL}. Provavelmente foi o bot manager (Akamai) "
        "limitando o seu IP — aguarde alguns minutos antes de tentar de novo ou troque de IP "
        "(VPN, hotspot). Reference: 18.abc.",
    )


def test_mensagem_substitui_o_texto_padrao():
    erro = BotChallengeBlockedError("TRF6", URL, bot_manager="F5", mensagem="desafio JavaScript")
    assert erro.args == ("desafio JavaScript",)
    assert (erro.tribunal, erro.url, erro.bot_manager, erro.reference) == ("TRF6", URL, "F5", None)


def test_waf_challenge_passa_a_propria_mensagem():
    renovado = WafChallengeError("TJPE", URL)
    sem_cookie = WafChallengeError("TJPE", URL, motivo="navegador ausente")
    (mensagem_renovado,) = renovado.args
    (mensagem_sem_cookie,) = sem_cookie.args
    assert "renovacao do cookie" in mensagem_renovado
    assert mensagem_sem_cookie.endswith("nao foi obtido: navegador ausente")
    assert "403" not in mensagem_renovado + mensagem_sem_cookie
    assert (renovado.tribunal, renovado.url) == ("TJPE", URL)


def test_desafio_f5_passa_a_propria_mensagem():
    erro = DesafioF5Error(URL)
    (mensagem,) = erro.args
    assert mensagem.startswith(f"O bot manager (F5) do TRF6 serviu um desafio JavaScript em {URL}")
    assert (erro.tribunal, erro.bot_manager) == ("TRF6", "F5")
