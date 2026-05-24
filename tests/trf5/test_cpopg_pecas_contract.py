"""Offline contract tests for ``TRF5Scraper.cpopg_download_pecas``.

Mirrors the TRF3 suite — the three TRF PJe deployments share the same
``documentoSemLoginHTML.seam?ca=...&idProcessoDoc=...`` URL shape, so the
extractor and downloader use the same logic per tribunal.
"""
from __future__ import annotations

import os

import pytest
import responses

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

LIST_URL = "https://pje1g.trf5.jus.br/pjeconsulta/ConsultaPublica/listView.seam"
DETAIL_URL = (
    "https://pje1g.trf5.jus.br/pjeconsulta/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
)
DOC_URL = (
    "https://pje1g.trf5.jus.br/pjeconsulta/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/documentoSemLoginHTML.seam"
)


def test_extract_documento_urls_finds_all_pecas_in_detail() -> None:
    from juscraper.courts.trf5.download import extract_documento_urls

    detail = load_sample_bytes("trf5", "cpopg/detail_normal.html").decode("latin-1")
    urls = extract_documento_urls(detail)
    assert len(urls) >= 1
    ids = [d for _, d in urls]
    assert len(ids) == len(set(ids))


def test_extract_documento_urls_empty_when_no_pecas() -> None:
    from juscraper.courts.trf5.download import extract_documento_urls

    assert extract_documento_urls("<html><body>nada</body></html>") == []


@responses.activate
def test_cpopg_download_pecas_writes_files_per_cnj(tmp_path) -> None:
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
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf5", "cpopg/detail_normal.html"),
        content_type="text/html",
    )
    doc_body = load_sample_bytes("trf5", "cpopg_pecas/documento_html.html")
    from juscraper.courts.trf5.download import extract_documento_urls
    n_pecas = len(
        extract_documento_urls(
            load_sample_bytes("trf5", "cpopg/detail_normal.html").decode("latin-1")
        )
    )
    for _ in range(n_pecas):
        responses.add(
            responses.GET, DOC_URL, body=doc_body, content_type="text/html"
        )

    scraper = jus.scraper("trf5", sleep_time=0, download_path=str(tmp_path))
    # Pick whatever CNJ the existing integration test uses — value is irrelevant
    # under responses, but keep it realistic for readability.
    paths = scraper.cpopg_download_pecas("08000350720234058000")

    assert len(paths) == 1
    saved = paths[0]
    assert len(saved) == n_pecas
    for p in saved:
        assert os.path.isfile(p)
        with open(p, "rb") as fh:
            assert fh.read() == doc_body


def test_cpopg_download_pecas_rejects_unknown_kwargs(tmp_path) -> None:
    scraper = jus.scraper("trf5", sleep_time=0, download_path=str(tmp_path))
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg_download_pecas(
            "08000350720234058000", filtro_inexistente="x"
        )
