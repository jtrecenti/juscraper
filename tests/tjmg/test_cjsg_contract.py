"""Offline contract tests for TJMG cjsg.

TJMG hits four endpoints in strict sequence per ``cjsg`` call:

1. ``GET formEspelhoAcordao.do`` — initial form (HTML).
2. ``GET captcha.svl?<timestamp>`` — 5-digit numeric captcha image
   (PNG). The scraper writes it to a temporary file and decodes it via
   ``txtcaptcha`` (lazy import, **not** in ``pyproject.toml``).
3. ``POST .../ValidacaoCaptchaAction.isCaptchaValid.dwr`` — DWR
   plaintext call validating the decoded captcha. Server flags the
   session; subsequent searches reuse it.
4. ``GET pesquisaPalavrasEspelhoAcordao.do?...`` — actual results
   (paginated by ``numeroRegistro = (pagina-1) * linhas_por_pagina + 1``).

Pytest never decodes the real captcha: the contract patches
``txtcaptcha`` into ``sys.modules`` with a stub that returns a fixed
5-digit code. The captured PNG sample is shipped as-is to keep the
contract close to live HTTP, but it's never read by the decoder under
test.

``OrderedRegistry`` is used because the four endpoints are URL-distinct
*per call*, but multi-page scenarios issue two GETs to the same
``pesquisaPalavrasEspelhoAcordao.do`` URL with different
``numeroRegistro`` query params; ordered matching keeps the contract
robust to the URL collision.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample_bytes, query_param_subset_matcher

BASE = "https://www5.tjmg.jus.br/jurisprudencia"
FORM_URL = f"{BASE}/formEspelhoAcordao.do"
CAPTCHA_IMG_URL = f"{BASE}/captcha.svl"
DWR_VALIDATE_URL = (
    f"{BASE}/dwr/call/plaincall/ValidacaoCaptchaAction.isCaptchaValid.dwr"
)
SEARCH_URL = f"{BASE}/pesquisaPalavrasEspelhoAcordao.do"

CJSG_MIN_COLUMNS = {
    "processo", "relator", "data_julgamento", "data_publicacao", "ementa",
}

_SAMPLES_DIR = Path(__file__).parent / "samples" / "cjsg"
pytestmark = pytest.mark.skipif(
    not (_SAMPLES_DIR / "form_acordao.html").exists(),
    reason=(
        "TJMG samples ainda não capturados — rode "
        "`pip install txtcaptcha && python -m tests.fixtures.capture.tjmg` "
        "para popular tests/tjmg/samples/cjsg/."
    ),
)


@pytest.fixture
def mock_txtcaptcha(mocker):
    """Patch ``txtcaptcha`` into ``sys.modules`` with a static stub.

    The lazy ``import txtcaptcha`` inside ``_solve_captcha`` resolves
    against this fake module; ``decrypt`` always returns ``["12345"]``.
    """
    fake = MagicMock()
    fake.decrypt = MagicMock(return_value=["12345"])
    mocker.patch.dict(sys.modules, {"txtcaptcha": fake})


def _add_form():
    responses.add(
        responses.GET,
        FORM_URL,
        body=load_sample_bytes("tjmg", "cjsg/form_acordao.html"),
        status=200,
        content_type="text/html; charset=ISO-8859-1",
    )


def _add_captcha():
    """Match any ``captcha.svl?<timestamp>``; query is dynamic."""
    responses.add(
        responses.GET,
        CAPTCHA_IMG_URL,
        body=load_sample_bytes("tjmg", "cjsg/captcha.png"),
        status=200,
        content_type="image/png",
    )


def _add_dwr():
    responses.add(
        responses.POST,
        DWR_VALIDATE_URL,
        body=load_sample_bytes("tjmg", "cjsg/dwr_validate.txt"),
        status=200,
        content_type="text/plain",
    )


def _add_search(sample_path: str, expected_query_subset: dict[str, str]):
    """Search GET; body is shipped as latin-1 bytes (the scraper sets
    ``resp.encoding = 'iso-8859-1'`` before reading ``resp.text``)."""
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=load_sample_bytes("tjmg", sample_path),
        status=200,
        content_type="text/html; charset=ISO-8859-1",
        match=[query_param_subset_matcher(expected_query_subset)],
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_typical_com_paginacao(mock_txtcaptcha, mocker):
    """Two-page query exercises ``numeroRegistro=1`` and ``numeroRegistro=11``."""
    mocker.patch("time.sleep")
    _add_form()
    _add_captcha()
    _add_dwr()
    _add_search("cjsg/results_normal_page_01.html", {"numeroRegistro": "1"})
    _add_search("cjsg/results_normal_page_02.html", {"numeroRegistro": "11"})

    df = jus.scraper("tjmg").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate(registry=OrderedRegistry)
def test_cjsg_single_page(mock_txtcaptcha, mocker):
    """Single page scenario (one search GET)."""
    mocker.patch("time.sleep")
    _add_form()
    _add_captcha()
    _add_dwr()
    _add_search("cjsg/single_page.html", {"numeroRegistro": "1"})

    df = jus.scraper("tjmg").cjsg(
        "homicidio qualificado dolo eventual", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate(registry=OrderedRegistry)
def test_cjsg_no_results(mock_txtcaptcha, mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    _add_form()
    _add_captcha()
    _add_dwr()
    _add_search("cjsg/no_results.html", {"numeroRegistro": "1"})

    df = jus.scraper("tjmg").cjsg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty
