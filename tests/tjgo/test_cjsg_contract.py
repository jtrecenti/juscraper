"""Offline contract tests for TJGO cjsg.

The Projudi search endpoint requires a GET on the form URL first to prime
session cookies; subsequent POSTs return ``iso-8859-1`` HTML. The contract
mocks both calls and asserts the form body sent on each page, including
the ``cf-turnstile-response=""`` literal (Cloudflare widget the backend
ignores).
"""
import pandas as pd
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


def _add_post(pesquisa: str, page: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample_bytes("tjgo", sample_path),
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
    assert CJSG_FIELDS <= set(df.columns)
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
    assert CJSG_FIELDS <= set(df.columns)
    assert len(df) == 1


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame (not an error)."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("juscraper_probe_zero_hits_xyzqwe", page=1,
              sample_path="cjsg/no_results.html")

    df = jus.scraper("tjgo").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_payload_carries_empty_turnstile_token(mocker):
    """The body must carry ``cf-turnstile-response`` empty (backend ignores it)."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.html")

    jus.scraper("tjgo").cjsg("dano moral", paginas=1)

    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert len(post_calls) == 1
    body = post_calls[0].request.body or ""
    assert "cf-turnstile-response=" in body
