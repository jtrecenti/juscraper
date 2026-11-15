"""Helpers compartilhados pelos contratos cjsg do TJMG.

Funções aqui são reusadas entre ``test_cjsg_contract.py`` e
``test_cjsg_filters_contract.py``. As três respostas pré-busca
(formulário, captcha, DWR) são idênticas em todo cenário; só o GET de
``pesquisaPalavrasEspelhoAcordao.do`` muda entre testes — e por isso
fica local. ``FALHAS_DE_REDE`` serve também ao ``test_cposg_contract.py``.
"""
from __future__ import annotations

import pytest
import requests
import responses

from tests._helpers import load_sample_bytes

BASE = "https://www5.tjmg.jus.br/jurisprudencia"
FORM_URL = f"{BASE}/formEspelhoAcordao.do"
CAPTCHA_IMG_URL = f"{BASE}/captcha.svl"
DWR_VALIDATE_URL = (
    f"{BASE}/dwr/call/plaincall/ValidacaoCaptchaAction.isCaptchaValid.dwr"
)
SEARCH_URL = f"{BASE}/pesquisaPalavrasEspelhoAcordao.do"

FALHAS_DE_REDE = [
    pytest.param(
        requests.exceptions.ChunkedEncodingError(
            ConnectionResetError(104, "Connection reset by peer")
        ),
        id="chunked-connection-reset",
    ),
    pytest.param(requests.ConnectionError("Connection reset by peer"), id="connection-error"),
    pytest.param(requests.ReadTimeout("read timeout=60"), id="read-timeout"),
]
"""Falhas de rede observadas no TJMG (#440), que os perfis HTTP retentam."""


def add_form() -> None:
    responses.add(
        responses.GET,
        FORM_URL,
        body=load_sample_bytes("tjmg", "cjsg/form_acordao.html"),
        status=200,
        content_type="text/html; charset=ISO-8859-1",
    )


def add_captcha() -> None:
    """Match qualquer ``captcha.svl?<timestamp>``; query é dinâmica."""
    responses.add(
        responses.GET,
        CAPTCHA_IMG_URL,
        body=load_sample_bytes("tjmg", "cjsg/captcha.png"),
        status=200,
        content_type="image/png",
    )


def add_dwr() -> None:
    responses.add(
        responses.POST,
        DWR_VALIDATE_URL,
        body=load_sample_bytes("tjmg", "cjsg/dwr_validate.txt"),
        status=200,
        content_type="text/plain",
    )
