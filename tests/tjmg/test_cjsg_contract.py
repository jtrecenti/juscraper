"""Offline contract tests for TJMG cjsg.

TJMG hits four endpoints in strict sequence per ``cjsg`` call:

1. ``GET formEspelhoAcordao.do`` — initial form (HTML).
2. ``GET captcha.svl?<timestamp>`` — 5-digit numeric captcha image
   (PNG). The scraper writes it to a temporary file and decodes it via
   ``txtcaptcha`` (lazy import; optional extra ``[tjmg]`` in
   ``pyproject.toml``).
3. ``POST .../ValidacaoCaptchaAction.isCaptchaValid.dwr`` — DWR
   plaintext call validating the decoded captcha. Server flags the
   session; subsequent searches reuse it.
4. ``GET pesquisaPalavrasEspelhoAcordao.do?...`` — actual results
   (paginated by ``numeroRegistro = (pagina-1) * tamanho_pagina + 1``).

Pytest never decodes the real captcha: the contract patches
``txtcaptcha`` into ``sys.modules`` with a stub that returns a fixed
5-digit code (fixture ``mock_txtcaptcha`` em ``conftest.py``). The
captured PNG sample is shipped as-is to keep the contract close to live
HTTP, but it's never read by the decoder under test.

``OrderedRegistry`` is used because the four endpoints are URL-distinct
*per call*, but multi-page scenarios issue two GETs to the same
``pesquisaPalavrasEspelhoAcordao.do`` URL with different
``numeroRegistro`` query params; ordered matching keeps the contract
robust to the URL collision.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import requests
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample_bytes, query_param_subset_matcher
from tests.tjmg._helpers import FORM_URL, SEARCH_URL, add_captcha, add_dwr, add_form

CJSG_MIN_COLUMNS = {
    "processo", "relator", "data_julgamento", "data_publicacao", "ementa",
}

_SAMPLES_DIR = Path(__file__).parent / "samples" / "cjsg"
pytestmark = pytest.mark.skipif(
    not (_SAMPLES_DIR / "form_acordao.html").exists(),
    reason=(
        "TJMG samples ainda não capturados — rode "
        "`uv pip install -e \".[tjmg]\" && python -m tests.fixtures.capture.tjmg` "
        "para popular tests/tjmg/samples/cjsg/."
    ),
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
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/results_normal_page_01.html", {"numeroRegistro": "1"})
    _add_search("cjsg/results_normal_page_02.html", {"numeroRegistro": "11"})

    df = jus.scraper("tjmg").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )
    assert df["processo"].nunique() > 1, (
        "todos os processos iguais — paginação suspeita"
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_single_page(mock_txtcaptcha, mocker):
    """Single page scenario (one search GET)."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/single_page.html", {"numeroRegistro": "1"})

    df = jus.scraper("tjmg").cjsg(
        "homicidio qualificado dolo eventual", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_no_results(mock_txtcaptcha, mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/no_results.html", {"numeroRegistro": "1"})

    df = jus.scraper("tjmg").cjsg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_revalida_captcha_quando_sessao_expira(mock_txtcaptcha, mocker):
    """HTTP 401 no meio da paginacao dispara nova validacao do captcha e repete a pagina."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/results_normal_page_01.html", {"numeroRegistro": "1"})
    responses.add(
        responses.GET,
        SEARCH_URL,
        status=401,
        match=[query_param_subset_matcher({"numeroRegistro": "11"})],
    )
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/results_normal_page_02.html", {"numeroRegistro": "11"})

    df = jus.scraper("tjmg").cjsg("dano moral", paginas=range(1, 3))

    assert df["processo"].nunique() > 10
    dwr_calls = [c for c in responses.calls if "isCaptchaValid" in c.request.url]
    assert len(dwr_calls) == 2


_FALHAS_DE_REDE = [
    pytest.param(
        requests.exceptions.ChunkedEncodingError(
            ConnectionResetError(104, "Connection reset by peer")
        ),
        id="chunked-connection-reset",
    ),
    pytest.param(requests.ConnectionError("Connection reset by peer"), id="connection-error"),
    pytest.param(requests.ReadTimeout("read timeout=60"), id="read-timeout"),
]


@pytest.mark.parametrize("falha", _FALHAS_DE_REDE)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_retenta_falha_de_rede_na_paginacao(mock_txtcaptcha, mocker, falha):
    """Conexao derrubada ou leitura lenta numa pagina ganha nova tentativa (#440)."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/results_normal_page_01.html", {"numeroRegistro": "1"})
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=falha,
        match=[query_param_subset_matcher({"numeroRegistro": "11"})],
    )
    _add_search("cjsg/results_normal_page_02.html", {"numeroRegistro": "11"})

    df = jus.scraper("tjmg").cjsg("dano moral", paginas=range(1, 3))

    assert df["processo"].nunique() > 10
    assert len([c for c in responses.calls if "numeroRegistro=11" in c.request.url]) == 2


@pytest.mark.parametrize("falha", _FALHAS_DE_REDE)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_retenta_falha_de_rede_no_formulario(mock_txtcaptcha, mocker, falha):
    """O ``ReadTimeout`` do notebook (#440) vinha do formulario e do captcha."""
    mocker.patch("time.sleep")
    responses.add(responses.GET, FORM_URL, body=falha)
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/single_page.html", {"numeroRegistro": "1"})

    df = jus.scraper("tjmg").cjsg("homicidio qualificado dolo eventual", paginas=1)

    assert len(df) > 0


@responses.activate(registry=OrderedRegistry)
def test_cjsg_falha_de_rede_persistente_sobe_a_excecao_original(mock_txtcaptcha, mocker):
    """Esgotadas as tentativas do perfil, a excecao de rede original sobe."""
    mocker.patch("time.sleep")
    scraper = jus.scraper("tjmg")
    for _ in range(scraper.perfis_http["cjsg"].max_retries):
        responses.add(responses.GET, FORM_URL, body=requests.ConnectionError("reset"))

    with pytest.raises(requests.ConnectionError, match="reset"):
        scraper.cjsg("dano moral", paginas=1)


@pytest.mark.parametrize(
    ("politica", "timeout"),
    [
        pytest.param(None, (10, 120), id="default"),
        pytest.param({"cjsg": {"timeout": 300}}, 300, id="politica"),
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_timeout_vem_do_perfil(mock_txtcaptcha, mocker, politica, timeout):
    """Todas as requisicoes do cjsg usam o timeout do perfil, ajustavel por ``politica=``."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/single_page.html", {"numeroRegistro": "1"})

    jus.scraper("tjmg", politica=politica).cjsg("homicidio", paginas=1)

    assert [c.request.req_kwargs["timeout"] for c in responses.calls] == [timeout] * 4
