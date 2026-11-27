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
from juscraper.core.base import _texto_ausente_como_none
from juscraper.core.exceptions import ColetaParcialError
from juscraper.courts.tjmg.client import TJMGScraper
from juscraper.courts.tjmg.parse import cjsg_parse
from tests._helpers import load_sample_bytes, query_param_subset_matcher, timeout_enviado, url_enviada
from tests.tjmg._helpers import FALHAS_DE_REDE, FORM_URL, SEARCH_URL, add_captcha, add_dwr, add_form

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
    dwr_calls = [c for c in responses.calls if "isCaptchaValid" in url_enviada(c.request)]
    assert len(dwr_calls) == 2



@pytest.mark.parametrize("falha", FALHAS_DE_REDE)
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
    assert len([c for c in responses.calls if "numeroRegistro=11" in url_enviada(c.request)]) == 2


@pytest.mark.parametrize("falha", FALHAS_DE_REDE)
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
    for _ in range(TJMGScraper.perfis_http["cjsg"].max_retries):
        responses.add(responses.GET, FORM_URL, body=requests.ConnectionError("reset"))

    with pytest.raises(requests.ConnectionError, match="reset"):
        jus.scraper("tjmg").cjsg("dano moral", paginas=1)


def _falha_persistente_na_pagina(numero_registro: str) -> None:
    for _ in range(TJMGScraper.perfis_http["cjsg"].max_retries):
        responses.add(
            responses.GET,
            SEARCH_URL,
            body=requests.ConnectionError("reset"),
            match=[query_param_subset_matcher({"numeroRegistro": numero_registro})],
        )


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@responses.activate(registry=OrderedRegistry)
def test_cjsg_falha_persistente_numa_pagina_guarda_as_anteriores(mock_txtcaptcha, mocker, metodo):
    """Pagina 3 falha de vez: as paginas 1 e 2 vem lidas em ``.resultado``, e a busca para."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/results_normal_page_01.html", {"numeroRegistro": "1"})
    _add_search("cjsg/results_normal_page_02.html", {"numeroRegistro": "11"})
    _falha_persistente_na_pagina("21")

    with pytest.raises(ColetaParcialError, match=r"página 3 falhou.*faltam as páginas range\(3, 6\),") as erro:
        getattr(jus.scraper("tjmg"), metodo)("dano moral", paginas=range(1, 6))

    esperado = _texto_ausente_como_none(cjsg_parse(
        [load_sample_bytes("tjmg", f"cjsg/results_normal_page_0{n}.html").decode("iso-8859-1") for n in (1, 2)]
    ))
    pd.testing.assert_frame_equal(erro.value.resultado, esperado)
    assert isinstance(erro.value.__cause__, requests.ConnectionError)
    assert [type(f[2]) for f in erro.value.falhas] == [requests.ConnectionError]
    assert not [c for c in responses.calls if "numeroRegistro=31" in url_enviada(c.request)]


@responses.activate(registry=OrderedRegistry)
def test_cjsg_falha_persistente_sem_pagina_baixada_sobe_a_excecao_original(mock_txtcaptcha, mocker):
    """Sem pagina pedida ja baixada, nao ha parcial a guardar: a excecao de rede sobe."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search("cjsg/results_normal_page_01.html", {"numeroRegistro": "1"})
    _falha_persistente_na_pagina("11")

    with pytest.raises(requests.ConnectionError, match="reset"):
        jus.scraper("tjmg").cjsg("dano moral", paginas=[2, 3])


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

    assert [timeout_enviado(c.request) for c in responses.calls] == [timeout] * 4
