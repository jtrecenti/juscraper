"""Mensagem de ``BotChallengeBlockedError`` e das subclasses que descrevem outro sintoma."""
from __future__ import annotations

import copy
import pickle

import pytest

from juscraper.core.exceptions import (
    BotChallengeBlockedError,
    InvalidJSONResponseError,
    RetryExhaustedError,
    WafChallengeError,
)
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
    assert renovado.bot_manager == sem_cookie.bot_manager == "AWS WAF"


def test_desafio_f5_passa_a_propria_mensagem():
    erro = DesafioF5Error(URL)
    (mensagem,) = erro.args
    assert mensagem.startswith(f"O bot manager (F5) do TRF6 serviu um desafio JavaScript em {URL}")
    assert (erro.tribunal, erro.bot_manager) == ("TRF6", "F5")


@pytest.mark.parametrize(
    "erro",
    [
        BotChallengeBlockedError("TRF3", URL, reference="18.abc"),
        BotChallengeBlockedError("Falcao", URL, bot_manager="CloudFront", mensagem="bloqueio"),
        WafChallengeError("TJPE", URL, motivo="navegador ausente"),
        DesafioF5Error(URL),
        InvalidJSONResponseError(URL, 200, 3, content_type="text/html", snippet="<html>"),
        RetryExhaustedError(503, 3),
    ],
    ids=["padrao", "mensagem", "waf", "f5", "json", "retry"],
)
@pytest.mark.parametrize("copiar", [lambda e: pickle.loads(pickle.dumps(e)), copy.copy, copy.deepcopy])
def test_erro_com_init_proprio_sobrevive_a_pickle_e_copy(erro, copiar):
    """``args`` só guarda a mensagem; o ``__init__`` pede outros argumentos."""
    copia = copiar(erro)
    assert type(copia) is type(erro)
    assert copia.args == erro.args
    assert vars(copia) == vars(erro)
