"""Offline contract tests for TRF5 ``cpopg`` (PJe consulta pública).

Same shape as ``tests/trf3/test_cpopg_contract.py``. Distinct from the TRF3
suite to keep sample fixtures and matchers independent — TRF5 ships
slightly different form field IDs (``j_id156`` vs ``j_id165``) and a
``classeProcessual`` popup field instead of an autocomplete.
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

LIST_URL = "https://pje1g.trf5.jus.br/pjeconsulta/ConsultaPublica/listView.seam"
DETAIL_URL = (
    "https://pje1g.trf5.jus.br/pjeconsulta/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
)


@responses.activate
def test_cpopg_returns_dataframe_with_canonical_columns() -> None:
    """Happy path: one CNJ → one row with parties, movements and documents."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf5", "cpopg/form_initial.html"),
        content_type="text/html; charset=utf-8",
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf5", "cpopg/search_one_result.html"),
        content_type="text/xml; charset=utf-8",
        match=[
            _subset_form_matcher(
                {
                    "fPP:numProcesso-inputNumeroProcessoDecoration:"
                    "numProcesso-inputNumeroProcesso": "0058457-31.2025.4.05.8000",
                    "AJAXREQUEST": "_viewRoot",
                    "fPP:j_id224": "fPP:j_id224",
                    "fPP:j_id183:classeProcessualProcessoHidden": "",
                },
            ),
        ],
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf5", "cpopg/detail_normal.html"),
        content_type="text/html",
    )

    scraper = jus.scraper("trf5", sleep_time=0)
    df = scraper.cpopg("00584573120254058000")

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
    assert row["id_cnj"] == "00584573120254058000"
    assert row["processo"] == "0058457-31.2025.4.05.8000"
    # TRF5 sample has 2 active polo (party + lawyer) and 1 passive (defendant).
    assert isinstance(row["polo_ativo"], list) and len(row["polo_ativo"]) >= 1
    assert isinstance(row["polo_passivo"], list) and len(row["polo_passivo"]) >= 1


@responses.activate
def test_cpopg_missing_process_returns_row_with_only_id_cnj() -> None:
    """Missing CNJ yields one row keyed by ``id_cnj``, no extra HTTP fetch."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf5", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf5", "cpopg/search_no_results.html"),
    )

    scraper = jus.scraper("trf5", sleep_time=0)
    df = scraper.cpopg("00000000020994050000")
    assert len(df) == 1
    assert df.iloc[0]["id_cnj"] == "00000000020994050000"


def test_cpopg_rejects_unknown_kwargs() -> None:
    """Passing an unknown kwarg surfaces as a friendly ``TypeError``."""
    scraper = jus.scraper("trf5", sleep_time=0)
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg("00584573120254058000", magistrado="x")
