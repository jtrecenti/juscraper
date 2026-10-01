"""Deteccao do desafio do AWS WAF e mensagens do helper compartilhado.

A obtencao do cookie com um Playwright falso e exercitada em
``tests/stf/test_waf.py``, pelo invólucro do STF.
"""
from __future__ import annotations

import sys

import pytest
import requests

from juscraper.core.waf import eh_desafio_waf, obter_waf_token


def _resposta(status: int, corpo: bytes = b"", headers: dict | None = None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = corpo  # pylint: disable=protected-access
    resp.headers.update(headers or {})
    return resp


@pytest.mark.parametrize(
    ("status", "corpo", "headers", "esperado"),
    [
        (202, b"", {"x-amzn-waf-action": "challenge"}, True),
        (405, b"", {"x-amzn-waf-action": "challenge"}, True),
        (202, b"<script>window.gokuProps = {}</script>", {}, True),
        (202, b"<script>window.awsWafCookieDomainList = []</script>", {}, True),
        (202, b"<html>aceito</html>", {}, False),
        (200, b"<script>window.gokuProps = {}</script>", {}, False),
        (200, b"<html>formulario</html>", {}, False),
    ],
)
def test_eh_desafio_waf(status, corpo, headers, esperado):
    assert eh_desafio_waf(_resposta(status, corpo, headers)) is esperado


def test_sem_playwright_cita_o_tribunal_e_o_extra(mocker):
    mocker.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None})

    with pytest.raises(ImportError) as caught:
        obter_waf_token("https://exemplo.invalid/", tribunal="TJPE")

    mensagem = str(caught.value)
    assert "TJPE" in mensagem
    assert "juscraper[waf]" in mensagem
    assert "jus.scraper" not in mensagem


def test_alternativa_entra_na_mensagem(mocker):
    mocker.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None})

    with pytest.raises(ImportError, match="passe um cookie"):
        obter_waf_token("https://exemplo.invalid/", tribunal="STF", alternativa="Ou passe um cookie.")
