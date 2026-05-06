"""Offline contract tests for TRF3 ``cpopg`` (PJe consulta pública).

Validates the public API shape of :class:`TRF3Scraper` end-to-end with the
HTTP layer mocked via ``responses``: a real form HTML primes field-ID
extraction, a real Ajax fragment provides the ``ca`` token and a real detail
page produces the parsed record. Anything that drifts in the live deployment
breaks the capture script (``tests/fixtures/capture/trf3.py``) first; this
test then catches schema/parse regressions on the captured bytes.
"""
from __future__ import annotations

from urllib.parse import parse_qsl

import pandas as pd
import pytest
import responses

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes


def _subset_form_matcher(expected: dict[str, str]):
    """``responses`` 0.x lacks ``strict_match`` — homemade subset matcher."""

    def _match(request) -> tuple[bool, str]:
        body = request.body or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        actual = dict(parse_qsl(body, keep_blank_values=True))
        for key, value in expected.items():
            if actual.get(key) != value:
                return False, (
                    f"expected {key!r}={value!r}, got {actual.get(key)!r}"
                )
        return True, ""

    return _match

LIST_URL = "https://pje1g.trf3.jus.br/pje/ConsultaPublica/listView.seam"
DETAIL_URL = (
    "https://pje1g.trf3.jus.br/pje/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
)


def test_extract_movs_pagination_returns_none_when_no_slider() -> None:
    """Processes with ≤ 15 movs render no slider — paginator must short-circuit."""
    from juscraper.courts.trf3.download import extract_movs_pagination

    detail = load_sample_bytes("trf3", "cpopg/detail_normal.html").decode("latin-1")
    assert extract_movs_pagination(detail) is None


def test_extract_movs_pagination_picks_movs_slider_not_documentos() -> None:
    """Detail HTML has two Richfaces sliders (movs + docs). We must hit movs."""
    from juscraper.courts.trf3.download import extract_movs_pagination

    detail = load_sample_bytes("trf3", "cpopg/detail_paginated.html").decode("latin-1")
    info = extract_movs_pagination(detail)
    assert info is not None
    # The movs panel wrapper is ``j_id<NN>:j_id<NN>``; we don't pin the exact
    # ``j_id`` numbers (they're regenerated on every PJe redeploy), but the
    # structure does need to look right.
    assert info.max_pages > 1
    assert info.container_id != info.form_id
    assert info.slider_input_name.startswith(info.form_id + ":")
    assert info.ajax_source_name.startswith(info.form_id + ":")
    assert info.view_state  # ViewState is required for the AJAX POST


def test_merge_movs_pages_appends_rows_into_movs_tbody() -> None:
    """Splicing page-2 rows into page-1 tbody yields a single contiguous list."""
    from juscraper.courts.trf3.download import merge_movs_pages
    from juscraper.courts.trf3.parse import parse_detail

    detail = load_sample_bytes("trf3", "cpopg/detail_paginated.html").decode("latin-1")
    page_2 = load_sample_bytes("trf3", "cpopg/movs_page_2.html").decode("latin-1")
    page1_movs = parse_detail(detail)["movimentacoes"]
    merged_movs = parse_detail(merge_movs_pages(detail, [page_2]))["movimentacoes"]
    # Page 1 has 15 rows, page 2 has another 15 — merged must hold both.
    assert len(page1_movs) == 15
    assert len(merged_movs) == 30
    # The first 15 are unchanged (we append at the end of the tbody).
    assert merged_movs[:15] == page1_movs


def test_merge_movs_pages_noop_when_extras_empty() -> None:
    """No extra pages → identical HTML, identical parse."""
    from juscraper.courts.trf3.download import merge_movs_pages

    detail = load_sample_bytes("trf3", "cpopg/detail_paginated.html").decode("latin-1")
    assert merge_movs_pages(detail, []) is detail


@responses.activate
def test_cpopg_returns_dataframe_with_canonical_columns() -> None:
    """Happy path: one CNJ → one row, canonical columns populated."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf3", "cpopg/form_initial.html"),
        content_type="text/html; charset=utf-8",
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf3", "cpopg/search_one_result.html"),
        content_type="text/xml; charset=utf-8",
        match=[
            _subset_form_matcher(
                {
                    "fPP:numProcesso-inputNumeroProcessoDecoration:"
                    "numProcesso-inputNumeroProcesso": "5005946-09.2025.4.03.6324",
                    "AJAXREQUEST": "_viewRoot",
                    "fPP:j_id247": "fPP:j_id247",
                    "fPP:dataAutuacaoDecoration:dataAutuacaoInicioInputDate": "",
                },
            ),
        ],
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf3", "cpopg/detail_normal.html"),
        content_type="text/html",
    )

    scraper = jus.scraper("trf3", sleep_time=0)
    df = scraper.cpopg("50059460920254036324")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    expected = {
        "id_cnj",
        "processo",
        "classe",
        "assunto",
        "data_distribuicao",
        "orgao_julgador",
        "polo_ativo",
        "polo_passivo",
        "movimentacoes",
        "documentos",
    }
    assert expected <= set(df.columns)
    row = df.iloc[0]
    assert row["id_cnj"] == "50059460920254036324"
    assert row["processo"] == "5005946-09.2025.4.03.6324"
    assert row["classe"] is not None
    assert isinstance(row["movimentacoes"], list) and len(row["movimentacoes"]) > 0


@responses.activate
def test_cpopg_missing_process_returns_row_with_only_id_cnj() -> None:
    """A CNJ that PJe can't find still yields a row keyed by ``id_cnj``."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf3", "cpopg/form_initial.html"),
        content_type="text/html; charset=utf-8",
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf3", "cpopg/search_no_results.html"),
        content_type="text/xml; charset=utf-8",
    )
    # No detail URL is added — the scraper must short-circuit when there's
    # no ca token. Adding an unmocked URL would surface as ConnectionError
    # if the short-circuit ever regressed.

    scraper = jus.scraper("trf3", sleep_time=0)
    df = scraper.cpopg("00000000020994030000")

    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == "00000000020994030000"
    assert pd.isna(row.get("processo")) or row.get("processo") is None


@responses.activate
def test_cpopg_batch_lookup_preserves_order() -> None:
    """Mixed found/missing batch yields one row per input CNJ in order."""
    # ``GET form`` is fetched once at session init and memoized; subsequent
    # POSTs/GET-detail responses must be queued in submission order via
    # responses.add to enforce sequencing.
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf3", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf3", "cpopg/search_one_result.html"),
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf3", "cpopg/detail_normal.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf3", "cpopg/search_no_results.html"),
    )

    scraper = jus.scraper("trf3", sleep_time=0)
    df = scraper.cpopg(["50059460920254036324", "00000000020994030000"])
    assert list(df["id_cnj"]) == ["50059460920254036324", "00000000020994030000"]
    assert df.iloc[0]["processo"] == "5005946-09.2025.4.03.6324"
    assert df.iloc[1].get("processo") in (None,) or pd.isna(df.iloc[1].get("processo"))


def test_cpopg_rejects_unknown_kwargs() -> None:
    """Passing an unknown kwarg surfaces as a friendly ``TypeError``."""
    scraper = jus.scraper("trf3", sleep_time=0)
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg("50059460920254036324", filtro_inexistente="x")


@responses.activate
def test_cpopg_batch_continues_after_download_error() -> None:
    """Erro de rede num CNJ não derruba o batch — vira linha só com ``id_cnj``."""
    # GET form OK + 1 POST que dá ConnectionError + 1 POST OK + 1 GET detail OK.
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf3", "cpopg/form_initial.html"),
    )
    responses.add(responses.POST, LIST_URL, body=ConnectionError("kaboom"))
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf3", "cpopg/search_one_result.html"),
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf3", "cpopg/detail_normal.html"),
    )

    scraper = jus.scraper("trf3", sleep_time=0)
    df = scraper.cpopg(["00000000020994030000", "50059460920254036324"])
    assert list(df["id_cnj"]) == ["00000000020994030000", "50059460920254036324"]
    # CNJ que falhou no download vira linha só com id_cnj.
    assert pd.isna(df.iloc[0].get("processo")) or df.iloc[0].get("processo") is None
    # CNJ que veio depois é parseado normalmente.
    assert df.iloc[1]["processo"] == "5005946-09.2025.4.03.6324"


@responses.activate
def test_cpopg_batch_continues_after_parse_error(monkeypatch) -> None:
    """Erro no parser de um item vira linha só com ``id_cnj`` e o batch segue."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf3", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf3", "cpopg/search_one_result.html"),
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf3", "cpopg/detail_normal.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf3", "cpopg/search_one_result.html"),
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf3", "cpopg/detail_normal.html"),
    )

    # Faz o parser explodir só na primeira chamada.
    from juscraper.courts.trf3 import client as trf3_client

    real_parse = trf3_client.parse_detail
    calls = {"n": 0}

    def flaky_parse(html):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("HTML inesperado")
        return real_parse(html)

    monkeypatch.setattr(trf3_client, "parse_detail", flaky_parse)

    scraper = jus.scraper("trf3", sleep_time=0)
    df = scraper.cpopg(["50059460920254036324", "50059460920254036325"])
    assert list(df["id_cnj"]) == ["50059460920254036324", "50059460920254036325"]
    assert pd.isna(df.iloc[0].get("processo")) or df.iloc[0].get("processo") is None
    assert df.iloc[1]["processo"] == "5005946-09.2025.4.03.6324"
