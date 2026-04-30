"""Offline contract tests for TJPB cjsg.

The TJPB Laravel/PJe search requires a GET on the homepage to extract
the ``_token`` CSRF meta value, which is then sent inside the JSON body
of every search POST. Each contract test mocks the GET (returning a
captured home.html with a stable meta tag) and the POST(s).
"""
import pandas as pd
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjpb.download import BASE_URL, SEARCH_URL, TOKEN_RE, build_cjsg_payload
from tests._helpers import load_sample, load_sample_bytes

CJSG_FIELDS = {"processo", "ementa", "data_julgamento"}

_HOME_HTML_BYTES = load_sample_bytes("tjpb", "cjsg/home.html")
_TOKEN_MATCH = TOKEN_RE.search(_HOME_HTML_BYTES.decode("utf-8"))
assert _TOKEN_MATCH is not None, "captured TJPB home.html lacks <meta name='_token' ...>"
_TOKEN = _TOKEN_MATCH.group(1)


def _add_get_home() -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=_HOME_HTML_BYTES,
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_post(pesquisa: str, page: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpb", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(
            build_cjsg_payload(token=_TOKEN, pesquisa=pesquisa, page=page),
        )],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """GET home (token) + two POSTs (page 1 and 2)."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.json")
    _add_post("dano moral", page=2, sample_path="cjsg/results_normal_page_02.json")

    df = jus.scraper("tjpb").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_FIELDS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single-page query: GET home + one POST."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post("usucapiao extraordinario imovel rural",
              page=1, sample_path="cjsg/single_page.json")

    df = jus.scraper("tjpb").cjsg(
        "usucapiao extraordinario imovel rural", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert CJSG_FIELDS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame (not an error)."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post("juscraper_probe_zero_hits_xyzqwe",
              page=1, sample_path="cjsg/no_results.json")

    df = jus.scraper("tjpb").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_token_propagates_into_body(mocker):
    """The CSRF token from the home page must reach the JSON body's ``_token`` key."""
    mocker.patch("time.sleep")
    _add_get_home()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.json")

    jus.scraper("tjpb").cjsg("dano moral", paginas=1)

    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert len(post_calls) == 1
    body = post_calls[0].request.body
    assert isinstance(body, (bytes, bytearray))
    assert _TOKEN.encode() in body
