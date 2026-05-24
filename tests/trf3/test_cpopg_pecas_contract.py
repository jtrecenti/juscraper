"""Offline contract tests for ``TRF3Scraper.cpopg_download_pecas``.

Validates the peças-download flow end-to-end with HTTP mocked via ``responses``:
the detail HTML carries the ``documentoSemLoginHTML.seam?ca=...&idProcessoDoc=...``
links, the scraper extracts them and issues one GET per peça. The asserted
side-effect is the file layout on disk (``<dir>/<cnj>/<id>.html``) and the
contents of each saved file.
"""
from __future__ import annotations

import os

import pytest
import responses

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

LIST_URL = "https://pje1g.trf3.jus.br/pje/ConsultaPublica/listView.seam"
DETAIL_URL = (
    "https://pje1g.trf3.jus.br/pje/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
)
DOC_URL = (
    "https://pje1g.trf3.jus.br/pje/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/documentoSemLoginHTML.seam"
)


def test_extract_documento_urls_finds_all_pecas_in_detail() -> None:
    """Detail HTML must yield one ``(ca, id_processo_doc)`` per peça juntada."""
    from juscraper.courts.trf3.download import extract_documento_urls

    detail = load_sample_bytes("trf3", "cpopg/detail_normal.html").decode("latin-1")
    urls = extract_documento_urls(detail)
    # Sample has 2 peças in the documentos table; dedup is by idProcessoDoc.
    assert len(urls) >= 1
    assert all(isinstance(ca, str) and isinstance(doc_id, str) for ca, doc_id in urls)
    # IDs are numeric strings; tokens are hex.
    for ca, doc_id in urls:
        assert doc_id.isdigit()
        assert all(c in "0123456789abcdef" for c in ca)
    # No duplicates by id_processo_doc.
    ids = [d for _, d in urls]
    assert len(ids) == len(set(ids))


def test_extract_documento_urls_empty_when_no_pecas() -> None:
    """A detail HTML without documentos must yield an empty list."""
    from juscraper.courts.trf3.download import extract_documento_urls

    assert extract_documento_urls("<html><body>nada aqui</body></html>") == []


@responses.activate
def test_cpopg_download_pecas_writes_files_per_cnj(tmp_path) -> None:
    """Happy path: detail → list peças → GET each → file written to disk."""
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
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf3", "cpopg/detail_normal.html"),
        content_type="text/html",
    )
    doc_body = load_sample_bytes("trf3", "cpopg_pecas/documento_html.html")
    # Mock all peça GETs — the sample has 2 documentos juntados.
    responses.add(responses.GET, DOC_URL, body=doc_body, content_type="text/html")
    responses.add(responses.GET, DOC_URL, body=doc_body, content_type="text/html")

    scraper = jus.scraper("trf3", sleep_time=0, download_path=str(tmp_path))
    paths = scraper.cpopg_download_pecas("50059460920254036324")

    assert len(paths) == 1
    saved = paths[0]
    assert len(saved) == 2  # two peças in the sample
    for p in saved:
        assert os.path.isfile(p)
        assert p.endswith(".html")
        with open(p, "rb") as fh:
            assert fh.read() == doc_body
    # Folder layout: <tmp>/<cnj>/<id>.html
    proc_dir = tmp_path / "50059460920254036324"
    assert proc_dir.is_dir()


@responses.activate
def test_cpopg_download_pecas_missing_process_returns_empty_list(tmp_path) -> None:
    """A CNJ that PJe can't find still appears in the output, with an empty list."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf3", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf3", "cpopg/search_no_results.html"),
    )
    # No DETAIL/DOC mocks — must short-circuit when there's no ca token.

    scraper = jus.scraper("trf3", sleep_time=0, download_path=str(tmp_path))
    paths = scraper.cpopg_download_pecas("00000000020994030000")
    assert paths == [[]]


def test_cpopg_download_pecas_rejects_unknown_kwargs(tmp_path) -> None:
    scraper = jus.scraper("trf3", sleep_time=0, download_path=str(tmp_path))
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg_download_pecas(
            "50059460920254036324", filtro_inexistente="x"
        )


@responses.activate
def test_cpopg_download_pecas_continues_after_peca_error(tmp_path) -> None:
    """Falha numa peça não derruba o processo — as outras peças são salvas."""
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
    # Primeira peça: erro 500. Segunda: OK.
    responses.add(responses.GET, DOC_URL, status=500)
    doc_body = load_sample_bytes("trf3", "cpopg_pecas/documento_html.html")
    responses.add(responses.GET, DOC_URL, body=doc_body, content_type="text/html")

    scraper = jus.scraper("trf3", sleep_time=0, download_path=str(tmp_path))
    paths = scraper.cpopg_download_pecas("50059460920254036324")
    # Só a segunda peça foi salva.
    assert len(paths[0]) == 1
    assert os.path.isfile(paths[0][0])
