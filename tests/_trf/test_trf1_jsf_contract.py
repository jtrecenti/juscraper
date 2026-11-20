"""Contratos da família ``_trf`` com o portal JSF do TRF1 (capturado antes da troca para a API).

Os testes eram do ``TRF1Scraper``; com a troca do TRF1 para a API JSON, passam
a usar :class:`TRF1JSFScraper`, uma instalação da família com o endereço antigo.
"""
from __future__ import annotations

from urllib.parse import parse_qsl

import pandas as pd
import pytest
import responses

from juscraper.courts._trf.base import TRFConsultaScraper
from juscraper.courts._trf.download import DETAIL_PATH, extract_movs_pagination, fetch_movs_page, merge_movs_pages
from juscraper.courts._trf.parse import parse_detail
from tests._helpers import load_sample, load_sample_bytes


class TRF1JSFScraper(TRFConsultaScraper):
    """Instalação JSF do TRF1 antes da troca para a API (nov/2026), com os samples ``trf1_*``.

    O TRF1 saiu da família, mas os samples do portal JSF dele seguem exercitando
    o código da família ``_trf`` que o TRF5 e o TJPE usam.
    """

    BASE_URL = "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"
    TRIBUNAL_NAME = "TRF1"


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
    detail = load_sample_bytes("_trf", "cpopg/trf1_detail_normal.html").decode("latin-1")
    assert extract_movs_pagination(detail) is None


def test_extract_movs_pagination_picks_movs_slider() -> None:
    """Detail HTML with > 15 movs surfaces the slider coordinates we need."""
    detail = load_sample_bytes("_trf", "cpopg/trf1_detail_paginated.html").decode("latin-1")
    info = extract_movs_pagination(detail)
    assert info is not None
    assert info.max_pages > 1
    assert info.container_id != info.form_id
    assert info.slider_input_name.startswith(info.form_id + ":")
    assert info.ajax_source_name.startswith(info.form_id + ":")
    assert info.view_state


def test_merge_movs_pages_appends_rows_into_movs_tbody() -> None:
    """Splicing page-2 rows into page-1 tbody yields a single contiguous list."""
    # Page 1 (detail page) is latin-1; the AJAX page-2 fragment is UTF-8 — the
    # two endpoints of the same PJe deployment disagree on charset. Decode each
    # the way fetch_detail/fetch_movs_page do in production.
    detail = load_sample_bytes("_trf", "cpopg/trf1_detail_paginated.html").decode("latin-1")
    page_2 = load_sample_bytes("_trf", "cpopg/trf1_movs_page_2.html").decode("utf-8")
    page1_movs = parse_detail(detail)["movimentacoes"]
    merged_movs = parse_detail(merge_movs_pages(detail, [page_2]))["movimentacoes"]
    assert len(page1_movs) == 15
    assert len(merged_movs) == 30
    assert merged_movs[:15] == page1_movs
    # Regression guard: page-2 rows must carry clean accents, not mojibake.
    # Decoding the UTF-8 fragment as latin-1 turns "petição" into "petiÃ§Ã£o".
    page2_text = " ".join(m["descricao"] for m in merged_movs[15:])
    assert "Ã§" not in page2_text
    assert "Ã£" not in page2_text, (
        "mojibake nas movs paginadas — fragmento UTF-8 decodificado como latin-1"
    )


@responses.activate
def test_fetch_movs_page_decodes_fragment_as_utf8() -> None:
    """The Richfaces AJAX fragment is UTF-8; ``fetch_movs_page`` must not latin-1 it.

    Regression for the double-encoding bug where accented movimentação text came
    back mojibaked (``petição`` -> ``petiÃ§Ã£o``) because the UTF-8 partial
    response was decoded as latin-1. Serves the *raw bytes* of the captured
    fragment and asserts the decoded text carries clean accents.
    """
    detail = load_sample_bytes("_trf", "cpopg/trf1_detail_paginated.html").decode("latin-1")
    info = extract_movs_pagination(detail)
    assert info is not None

    scraper = TRF1JSFScraper(sleep_time=0)
    responses.add(
        responses.POST,
        scraper.BASE_URL + DETAIL_PATH,
        body=load_sample_bytes("_trf", "cpopg/trf1_movs_page_2.html"),  # raw UTF-8 bytes
        status=200,
        content_type="text/xml; charset=UTF-8",
    )

    fragment = fetch_movs_page(scraper, scraper.BASE_URL, info, 2, "ca-token")

    assert "ç" in fragment, "fragmento sem acento — decode suspeito"
    assert "Ã§" not in fragment
    assert "Ã£" not in fragment, (
        "mojibake: fragmento UTF-8 decodificado como latin-1"
    )


@responses.activate
def test_cpopg_returns_dataframe_with_canonical_columns() -> None:
    """Happy path: one CNJ → one row, canonical columns populated."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("_trf", "cpopg/trf1_form_initial.html"),
        content_type="text/html; charset=utf-8",
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("_trf", "cpopg/trf1_search_one_result.html"),
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
        body=load_sample_bytes("_trf", "cpopg/trf1_detail_normal.html"),
        content_type="text/html",
    )

    scraper = TRF1JSFScraper(sleep_time=0)
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
    assert row["orgao_julgador"] == "2ª Vara Federal Cível e Criminal da SSJ de Anápolis-GO"
    assert row["endereco_orgao"].startswith("Avenida Universitária, Quadra 02")
    assert isinstance(row["movimentacoes"], list)
    assert len(row["movimentacoes"]) > 0


@responses.activate
def test_cpopg_missing_process_returns_row_with_only_id_cnj() -> None:
    """A CNJ that PJe can't find still yields a row keyed by ``id_cnj``."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("_trf", "cpopg/trf1_form_initial.html"),
        content_type="text/html; charset=utf-8",
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("_trf", "cpopg/trf1_search_no_results.html"),
        content_type="text/xml; charset=utf-8",
    )

    scraper = TRF1JSFScraper(sleep_time=0)
    df = scraper.cpopg("00000000019994010000")

    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == "00000000019994010000"
    assert pd.isna(row.get("processo")) or row.get("processo") is None


def test_cpopg_rejects_unknown_kwargs() -> None:
    """Passing an unknown kwarg surfaces as a friendly ``TypeError``."""
    scraper = TRF1JSFScraper(sleep_time=0)
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg("10030632720234013304", filtro_inexistente="x")
