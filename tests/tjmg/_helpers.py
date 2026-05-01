"""Helpers compartilhados pelos contratos cjsg do TJMG.

Funções aqui são reusadas entre ``test_cjsg_contract.py`` e
``test_cjsg_filters_contract.py``. As três respostas pré-busca
(formulário, captcha, DWR) são idênticas em todo cenário; só o GET de
``pesquisaPalavrasEspelhoAcordao.do`` muda entre testes — e por isso
fica local.
"""
from __future__ import annotations

import responses

from tests._helpers import load_sample_bytes

BASE = "https://www5.tjmg.jus.br/jurisprudencia"
FORM_URL = f"{BASE}/formEspelhoAcordao.do"
CAPTCHA_IMG_URL = f"{BASE}/captcha.svl"
DWR_VALIDATE_URL = (
    f"{BASE}/dwr/call/plaincall/ValidacaoCaptchaAction.isCaptchaValid.dwr"
)
SEARCH_URL = f"{BASE}/pesquisaPalavrasEspelhoAcordao.do"


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
