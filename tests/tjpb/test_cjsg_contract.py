"""Offline contract tests for TJPB cjsg.

The TJPB Laravel/PJe search requires a GET on the classes API to establish
the session and receive the ``XSRF-TOKEN`` cookie, which is then sent in
the header of every search POST. Each contract test mocks the GET and POST(s).
"""
import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjpb.download import CLASSES_URL, SEARCH_URL, build_cjsg_payload
from tests._helpers import load_sample

CJSG_FIELDS = {"processo", "ementa", "data_julgamento"}

_XSRF_COOKIE = "contrato%2Fcsrf"
_LARAVEL_COOKIE = "contrato-session"
_CLASSES_RESPONSE = [{
    "id_classe_judicial": 53,
    "classe": "AGRAVO DE INSTRUMENTO (202)",
}]


def _add_get_classes(*, with_cookie: bool = True) -> None:
    headers = (
        [
            ("Set-Cookie", f"XSRF-TOKEN={_XSRF_COOKIE}; Path=/"),
            ("Set-Cookie", f"laravel_session={_LARAVEL_COOKIE}; Path=/"),
        ]
        if with_cookie else []
    )
    responses.add(
        responses.GET,
        CLASSES_URL,
        json=_CLASSES_RESPONSE,
        status=200,
        headers=headers,
    )


def _add_post(pesquisa: str, page: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpb", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(
            build_cjsg_payload(pesquisa=pesquisa, page=page),
        )],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """GET classes (CSRF cookie) + two POSTs (page 1 and 2)."""
    mocker.patch("time.sleep")
    _add_get_classes()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.json")
    _add_post("dano moral", page=2, sample_path="cjsg/results_normal_page_02.json")

    df = jus.scraper("tjpb").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_FIELDS
    assert len(df) > 0
    assert responses.calls[0].request.url == CLASSES_URL
    post_calls = [call for call in responses.calls if call.request.method == "POST"]
    assert len(post_calls) == 2
    assert all(call.request.headers["X-XSRF-TOKEN"] == "contrato/csrf" for call in post_calls)
    assert all("XSRF-TOKEN=contrato%2Fcsrf" in call.request.headers["Cookie"] for call in post_calls)
    assert all(f"laravel_session={_LARAVEL_COOKIE}" in call.request.headers["Cookie"] for call in post_calls)


@responses.activate
def test_cjsg_single_page(mocker):
    """Single-page query: GET classes + one POST."""
    mocker.patch("time.sleep")
    _add_get_classes()
    _add_post("usucapiao extraordinario imovel rural",
              page=1, sample_path="cjsg/single_page.json")

    df = jus.scraper("tjpb").cjsg(
        "usucapiao extraordinario imovel rural", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_FIELDS
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame (not an error)."""
    mocker.patch("time.sleep")
    _add_get_classes()
    _add_post("juscraper_probe_zero_hits_xyzqwe",
              page=1, sample_path="cjsg/no_results.json")

    df = jus.scraper("tjpb").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_xsrf_token_is_sent_in_header_and_not_body(mocker):
    """The CSRF cookie reaches the header, not the JSON body."""
    mocker.patch("time.sleep")
    _add_get_classes()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.json")

    jus.scraper("tjpb").cjsg("dano moral", paginas=1)

    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0].request.headers["X-XSRF-TOKEN"] == "contrato/csrf"
    assert "XSRF-TOKEN=contrato%2Fcsrf" in post_calls[0].request.headers["Cookie"]
    body = post_calls[0].request.body
    body = body.decode("utf-8") if isinstance(body, bytes) else body
    assert "_token" not in body


@responses.activate
def test_cjsg_falha_sem_cookie_xsrf(mocker):
    """Missing CSRF cookie produces an informative error before the POST."""
    mocker.patch("time.sleep")
    _add_get_classes(with_cookie=False)

    with pytest.raises(RuntimeError, match="XSRF-TOKEN"):
        jus.scraper("tjpb").cjsg("dano moral", paginas=1)

    assert [call.request.method for call in responses.calls] == ["GET"]
