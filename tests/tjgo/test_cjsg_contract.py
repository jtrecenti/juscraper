"""Offline contract tests for TJGO cjsg.

The Projudi search endpoint requires a GET on the form URL first to prime
session cookies; subsequent POSTs return ``iso-8859-1`` HTML. The contract
mocks both calls and asserts the form body sent on each page, including
the ``cf-turnstile-response=""`` literal. Since 12/11/2026 (Projudi 3.194.1)
the backend validates the Cloudflare Turnstile token and answers every search
without it with the empty form, so an empty search emits ``UserWarning``.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjgo.download import SEARCH_URL, build_cjsg_payload
from tests._helpers import load_sample_bytes

CJSG_FIELDS = {
    "processo", "id_arquivo", "serventia", "relator",
    "tipo_ato", "data_publicacao", "texto",
}


def _add_get_prime() -> None:
    responses.add(responses.GET, SEARCH_URL, body=b"", status=200)


def _add_post(pesquisa: str, page: int, sample_path: str, body: bytes | None = None) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=body if body is not None else load_sample_bytes("tjgo", sample_path),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_payload(pesquisa=pesquisa, page=page), allow_blank=True,
        )],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two pages: GET primes cookies, then two POSTs with matching bodies."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.html")
    _add_post("dano moral", page=2, sample_path="cjsg/results_normal_page_02.html")

    df = jus.scraper("tjgo").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_FIELDS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single-hit query: GET + a single POST."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("usucapiao extraordinario predio rural familia",
              page=1, sample_path="cjsg/single_page.html")

    df = jus.scraper("tjgo").cjsg(
        "usucapiao extraordinario predio rural familia", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_FIELDS
    assert len(df) == 1


@responses.activate
@pytest.mark.parametrize(
    ("pesquisa", "sample_path"),
    [
        ("juscraper_probe_zero_hits_xyzqwe", "cjsg/no_results.html"),
        # Resposta real a "dano moral" sem o token (Projudi 3.194.1).
        ("dano moral", "cjsg/blocked_turnstile.html"),
    ],
    ids=["sem_resultados", "bloqueada_pelo_turnstile"],
)
def test_cjsg_busca_vazia_avisa_do_turnstile(mocker, pesquisa, sample_path):
    """Empty search returns an empty DataFrame and warns about Turnstile.

    The portal answers a blocked search (no Turnstile token) the same way as
    a genuine zero-hit search, so every empty search warns.
    """
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post(pesquisa, page=1, sample_path=sample_path)

    with pytest.warns(UserWarning, match="Turnstile"):
        df = jus.scraper("tjgo").cjsg(pesquisa, paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_com_resultados_sem_contagem_nao_avisa(mocker):
    """Results on page 1 with an unreadable count are not a Turnstile block."""
    mocker.patch("time.sleep")
    mocker.patch("juscraper.courts.tjgo.download._extract_total", return_value=0)
    _add_get_prime()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.html")

    df = jus.scraper("tjgo").cjsg("dano moral", paginas=1)  # filterwarnings=error

    assert not df.empty


@responses.activate
def test_cjsg_resultado_com_atributos_na_div(mocker):
    """``<div class="search-result" data-...>`` still splits into result rows.

    The current portal HTML gives each result div ``data-realizador`` and
    ``data-id-arquivo`` after the class (issue #436). No recorded sample has
    them yet, because capturing one needs the Turnstile token; the test adds
    the attributes to the real page 1 sample.
    """
    mocker.patch("time.sleep")
    _add_get_prime()
    original = load_sample_bytes("tjgo", "cjsg/results_normal_page_01.html")
    com_atributos = original.replace(
        b'<div class="search-result">',
        b'<div class="search-result" data-realizador="1" data-id-arquivo="2">',
    )
    assert com_atributos != original
    _add_post("dano moral", page=1, sample_path="", body=com_atributos)
    esperado = jus.scraper("tjgo").cjsg_parse([original.decode("iso-8859-1")])
    assert len(esperado) == 10

    df = jus.scraper("tjgo").cjsg("dano moral", paginas=1)  # filterwarnings=error

    pd.testing.assert_frame_equal(df, esperado)


@responses.activate
def test_cjsg_payload_carries_empty_turnstile_token(mocker):
    """The body carries ``cf-turnstile-response`` empty (the scraper has no token)."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.html")

    jus.scraper("tjgo").cjsg("dano moral", paginas=1)

    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert len(post_calls) == 1
    body = post_calls[0].request.body or ""
    assert "cf-turnstile-response=" in body
