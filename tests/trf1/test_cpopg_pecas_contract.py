"""Offline contract tests for ``TRF1Scraper.cpopg(download_pecas=True, ...)``.

Mirrors the TRF3 suite — the three TRF PJe deployments share the same
``documentoSemLoginHTML.seam?ca=...&idProcessoDoc=...`` URL shape.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import responses

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

LIST_URL = (
    "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"
    "ConsultaPublica/listView.seam"
)
DETAIL_URL = (
    "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
)
DOC_URL = (
    "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/documentoSemLoginHTML.seam"
)


def test_extract_documento_urls_finds_all_pecas_in_detail() -> None:
    from juscraper.courts._trf.download import extract_documento_urls

    detail = load_sample_bytes("trf1", "cpopg/detail_normal.html").decode("latin-1")
    urls = extract_documento_urls(detail)
    assert len(urls) >= 1
    ids = [d for _, d in urls]
    assert len(ids) == len(set(ids))


def test_extract_documento_urls_empty_when_no_pecas() -> None:
    from juscraper.courts._trf.download import extract_documento_urls

    assert extract_documento_urls("<html><body>nada</body></html>") == []


def test_cpopg_default_does_not_download_pecas(tmp_path) -> None:
    scraper = jus.scraper("trf1", sleep_time=0, download_path=str(tmp_path))
    import inspect

    sig = inspect.signature(scraper.cpopg)
    assert sig.parameters["download_pecas"].default is False


@responses.activate
def test_cpopg_with_download_pecas_writes_files_and_adds_column(tmp_path) -> None:
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
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf1", "cpopg/detail_normal.html"),
        content_type="text/html",
    )
    doc_body = load_sample_bytes("trf1", "cpopg_pecas/documento_html.html")
    from juscraper.courts._trf.download import extract_documento_urls

    n_pecas = len(
        extract_documento_urls(
            load_sample_bytes("trf1", "cpopg/detail_normal.html").decode("latin-1")
        )
    )
    for _ in range(n_pecas):
        responses.add(
            responses.GET, DOC_URL, body=doc_body, content_type="text/html"
        )

    scraper = jus.scraper("trf1", sleep_time=0)
    df = scraper.cpopg(
        "10004080820254013602", download_pecas=True, diretorio=str(tmp_path)
    )
    assert "pecas" in df.columns
    saved = df.iloc[0]["pecas"]
    assert len(saved) == n_pecas
    for p in saved:
        assert Path(p).is_file()
