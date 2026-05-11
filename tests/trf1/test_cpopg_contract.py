"""Offline contract tests for TRF1 ``cpopg`` (PJe consulta pública).

Same shape as ``tests/trf3/test_cpopg_contract.py``. Distinct from the TRF3
suite to keep sample fixtures and matchers independent — TRF1 lives at a
different host (``pje1g-consultapublica.trf1.jus.br/consultapublica/``) and
the captured field IDs differ from TRF3's, even though the form structure
mirrors it (autocomplete ``classeJudicial`` + ``dataAutuacaoDecoration``).
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


LIST_URL = (
    "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"
    "ConsultaPublica/listView.seam"
)
DETAIL_URL = (
    "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
)


def test_extract_movs_pagination_returns_none_when_no_slider() -> None:
    """Processes with ≤ 15 movs render no slider — paginator must short-circuit."""
    from juscraper.courts.trf1.download import extract_movs_pagination

    detail = load_sample_bytes("trf1", "cpopg/detail_normal.html").decode("latin-1")
    assert extract_movs_pagination(detail) is None


def test_extract_movs_pagination_picks_movs_slider() -> None:
    """Detail HTML with > 15 movs surfaces the slider coordinates we need."""
    from juscraper.courts.trf1.download import extract_movs_pagination

    detail = load_sample_bytes("trf1", "cpopg/detail_paginated.html").decode("latin-1")
    info = extract_movs_pagination(detail)
    assert info is not None
    assert info.max_pages > 1
    assert info.container_id != info.form_id
    assert info.slider_input_name.startswith(info.form_id + ":")
    assert info.ajax_source_name.startswith(info.form_id + ":")
    assert info.view_state


def test_merge_movs_pages_appends_rows_into_movs_tbody() -> None:
    """Splicing page-2 rows into page-1 tbody yields a single contiguous list."""
    from juscraper.courts.trf1.download import merge_movs_pages
    from juscraper.courts.trf1.parse import parse_detail

    detail = load_sample_bytes("trf1", "cpopg/detail_paginated.html").decode("latin-1")
    page_2 = load_sample_bytes("trf1", "cpopg/movs_page_2.html").decode("latin-1")
    page1_movs = parse_detail(detail)["movimentacoes"]
    merged_movs = parse_detail(merge_movs_pages(detail, [page_2]))["movimentacoes"]
    assert len(page1_movs) == 15
    assert len(merged_movs) == 30
    assert merged_movs[:15] == page1_movs


@responses.activate
def test_cpopg_returns_dataframe_with_canonical_columns() -> None:
    """Happy path: one CNJ → one row, canonical columns populated."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf1", "cpopg/form_initial.html"),
        content_type="text/html; charset=utf-8",
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf1", "cpopg/search_one_result.html"),
        content_type="text/xml; charset=utf-8",
        match=[
            _subset_form_matcher(
                {
                    "fPP:numProcesso-inputNumeroProcessoDecoration:"
                    "numProcesso-inputNumeroProcesso": "1003063-27.2023.4.01.3304",
                    "AJAXREQUEST": "_viewRoot",
                    "fPP:j_id248": "fPP:j_id248",
                    "fPP:dataAutuacaoDecoration:dataAutuacaoInicioInputDate": "",
                },
            ),
        ],
    )
    # Use the no-slider detail so we don't need to mock paginator POSTs here.
    # Pagination is exercised by the unit tests above and the integration test.
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf1", "cpopg/detail_normal.html"),
        content_type="text/html",
    )

    scraper = jus.scraper("trf1", sleep_time=0)
    df = scraper.cpopg("10030632720234013304")

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
    assert row["id_cnj"] == "10030632720234013304"
    assert row["processo"] is not None
    assert isinstance(row["movimentacoes"], list) and len(row["movimentacoes"]) > 0


@responses.activate
def test_cpopg_missing_process_returns_row_with_only_id_cnj() -> None:
    """A CNJ that PJe can't find still yields a row keyed by ``id_cnj``."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf1", "cpopg/form_initial.html"),
        content_type="text/html; charset=utf-8",
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf1", "cpopg/search_no_results.html"),
        content_type="text/xml; charset=utf-8",
    )

    scraper = jus.scraper("trf1", sleep_time=0)
    df = scraper.cpopg("00000000019994010000")

    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == "00000000019994010000"
    assert pd.isna(row.get("processo")) or row.get("processo") is None


def test_cpopg_rejects_unknown_kwargs() -> None:
    """Passing an unknown kwarg surfaces as a friendly ``TypeError``."""
    scraper = jus.scraper("trf1", sleep_time=0)
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg("10030632720234013304", filtro_inexistente="x")
