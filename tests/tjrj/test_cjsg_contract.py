"""Offline contract tests for TJRJ cjsg.

The TJRJ flow has three steps: ``GET`` the ASPX form to extract hidden
fields, ``POST`` the form to seed the server-side session, then ``POST``
the JSON XHR per page. The contract mocks all three and pins the body
subset (everything except ``__VIEWSTATE`` / ``__VIEWSTATEGENERATOR`` /
``__EVENTVALIDATION`` — those rotate per request).
"""
import json

import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjrj.download import FORM_URL, RESULT_URL, build_cjsg_payload, extract_viewstate_fields
from tests._helpers import load_sample, urlencoded_body_subset_matcher

CJSG_FIELDS = {
    "processo", "classe", "orgao_julgador", "relator", "ementa",
    "data_julgamento", "data_publicacao", "cod_documento",
}


def _form_html() -> str:
    return load_sample("tjrj", "cjsg/post_initial.html")


def _xhr_payload(filename: str) -> dict:
    payload: dict = json.loads(load_sample("tjrj", f"cjsg/{filename}"))
    return payload


def _expected_body_subset(pesquisa: str, **overrides) -> dict:
    """Body keys we care about (drops the three rotating hidden fields).

    Built off ``build_cjsg_payload`` so the contract drifts with the source.
    """
    hidden = extract_viewstate_fields(_form_html())
    body = build_cjsg_payload(hidden=hidden, pesquisa=pesquisa, **overrides)
    body.pop("__VIEWSTATE", None)
    body.pop("__VIEWSTATEGENERATOR", None)
    body.pop("__EVENTVALIDATION", None)
    return body


def _add_form_get() -> None:
    responses.add(responses.GET, FORM_URL, body=_form_html(), status=200,
                  content_type="text/html; charset=utf-8")


def _add_form_post(pesquisa: str, **overrides) -> None:
    responses.add(
        responses.POST, FORM_URL, body=b"", status=200,
        match=[urlencoded_body_subset_matcher(_expected_body_subset(pesquisa, **overrides))],
    )


def _add_xhr(num_pagina_0: int, sample_filename: str) -> None:
    responses.add(
        responses.POST, RESULT_URL,
        json=_xhr_payload(sample_filename), status=200,
        match=[json_params_matcher({"numPagina": num_pagina_0, "pageSeq": "0"})],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query: GET, POST, two XHRs (numPagina=0 then 1)."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2024", ano_fim="2024")
    _add_xhr(0, "xhr_page_01.json")
    _add_xhr(1, "xhr_page_02.json")

    df = jus.scraper("tjrj").cjsg(
        "dano moral", ano_inicio=2024, ano_fim=2024, paginas=range(1, 3),
    )

    assert isinstance(df, pd.DataFrame)
    assert CJSG_FIELDS <= set(df.columns)
    assert len(df) == 20  # 10 docs/page × 2 páginas


@responses.activate
def test_cjsg_single_page(mocker):
    """Narrow query whose hits fit on a single XHR call."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post(
        "usucapiao extraordinario predio rural familia",
        ano_inicio="2024", ano_fim="2024",
    )
    _add_xhr(0, "xhr_single_page.json")

    df = jus.scraper("tjrj").cjsg(
        "usucapiao extraordinario predio rural familia",
        ano_inicio=2024, ano_fim=2024, paginas=1,
    )

    assert isinstance(df, pd.DataFrame)
    assert CJSG_FIELDS <= set(df.columns)
    assert len(df) == 2


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame, not an error."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post(
        "juscraper_probe_zero_hits_xyzqwe",
        ano_inicio="2024", ano_fim="2024",
    )
    _add_xhr(0, "xhr_no_results.json")

    df = jus.scraper("tjrj").cjsg(
        "juscraper_probe_zero_hits_xyzqwe",
        ano_inicio=2024, ano_fim=2024, paginas=1,
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_payload_carries_blocked_words_hidden(mocker):
    """The form POST must carry ``hfListaPalavrasBloqueadas`` (refs #143).

    The hidden field's absence triggered a transient 500 in 2026-04-30 — the
    contract pins it so a future regression that drops the field surfaces in
    CI rather than as a backend 500 in the wild.
    """
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2024", ano_fim="2024")
    _add_xhr(0, "xhr_page_01.json")

    jus.scraper("tjrj").cjsg(
        "dano moral", ano_inicio=2024, ano_fim=2024, paginas=1,
    )

    post_calls = [c for c in responses.calls if c.request.method == "POST"
                  and c.request.url.startswith(FORM_URL)]
    assert len(post_calls) == 1
    body = post_calls[0].request.body or ""
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    assert "ctl00%24ContentPlaceHolder1%24hfListaPalavrasBloqueadas=" in body
    # Value comes from the GET sample — non-empty stopword list.
    assert "ACIMA" in body  # one of the words in the canonical TJRJ stopword list
