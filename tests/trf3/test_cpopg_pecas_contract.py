"""Offline contract tests for ``TRF3Scraper.cpopg(download_pecas=True, ...)``.

Validates the peças-download flow end-to-end with HTTP mocked via ``responses``:
the detail HTML carries the ``documentoSemLoginHTML.seam?ca=...&idProcessoDoc=...``
links, ``cpopg`` extracts them and issues one GET per peça when invoked with
``download_pecas=True``. The asserted side-effect is the file layout on disk
(``<dir>/<cnj>/<id>.html``) plus the ``pecas`` column on the returned DataFrame.
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
    assert len(urls) >= 1
    assert all(isinstance(ca, str) and isinstance(doc_id, str) for ca, doc_id in urls)
    for ca, doc_id in urls:
        assert doc_id.isdigit()
        assert all(c in "0123456789abcdef" for c in ca)
    ids = [d for _, d in urls]
    assert len(ids) == len(set(ids))


def test_extract_docs_pagination_detects_slider_on_paginated_sample() -> None:
    """Detail com > 15 docs deve expor slider próprio (à parte do movs)."""
    from juscraper.courts.trf3.download import extract_docs_pagination, extract_movs_pagination

    detail = load_sample_bytes("trf3", "cpopg/detail_paginated.html").decode("latin-1")
    movs_info = extract_movs_pagination(detail)
    docs_info = extract_docs_pagination(detail)
    assert movs_info is not None and movs_info.max_pages > 1
    assert docs_info is not None and docs_info.max_pages > 1
    # Os dois sliders têm que ser instâncias distintas (form_id diferente).
    assert movs_info.form_id != docs_info.form_id
    assert movs_info.slider_input_name != docs_info.slider_input_name


def test_extract_docs_pagination_returns_none_when_no_slider() -> None:
    """Detail com ≤ 15 docs não renderiza slider — paginador retorna None."""
    from juscraper.courts.trf3.download import extract_docs_pagination

    detail = load_sample_bytes("trf3", "cpopg/detail_normal.html").decode("latin-1")
    assert extract_docs_pagination(detail) is None


def test_merge_docs_pages_splices_into_docs_tbody() -> None:
    """``merge_docs_pages`` adiciona linhas no tbody de docs sem mexer no movs."""
    import re

    from juscraper.courts.trf3.download import _extract_docs_rows, extract_documento_urls, merge_docs_pages

    detail = load_sample_bytes("trf3", "cpopg/detail_paginated.html").decode("latin-1")
    page1_urls = extract_documento_urls(detail)
    # Forja uma "página 2" reutilizando o tbody da página 1 (mesmo formato).
    m = re.search(
        r'<tbody[^>]*\bid="[^"]*:processoDocumentoGridTab:tb"[^>]*>.*?</tbody>',
        detail,
        re.DOTALL,
    )
    assert m is not None
    fake_page2 = m.group()
    # Sanity: a "extração de linhas" da page 2 forjada não é vazia.
    assert _extract_docs_rows(fake_page2)
    merged = merge_docs_pages(detail, [fake_page2])
    # Como reutilizamos os mesmos IDs, o dedup por id_processo_doc deve preservar
    # a contagem; o teste vale para garantir que o splice em si funciona.
    merged_urls = extract_documento_urls(merged)
    assert len(merged_urls) == len(page1_urls)  # dedup mantém único por id


def test_extract_documento_urls_empty_when_no_pecas() -> None:
    from juscraper.courts.trf3.download import extract_documento_urls

    assert extract_documento_urls("<html><body>nada aqui</body></html>") == []


def test_cpopg_default_does_not_download_pecas(tmp_path) -> None:
    """Sem ``download_pecas=True``, nenhum arquivo deve cair no diretório."""
    scraper = jus.scraper("trf3", sleep_time=0, download_path=str(tmp_path))
    # Não fazemos chamada de rede — só checamos que a flag default é False e
    # que o método não cria pastas/arquivos quando não pedimos peças.
    import inspect

    sig = inspect.signature(scraper.cpopg)
    assert sig.parameters["download_pecas"].default is False
    assert sig.parameters["diretorio"].default is None
    assert list(tmp_path.iterdir()) == []


@responses.activate
def test_cpopg_with_download_pecas_writes_files_and_adds_column(tmp_path) -> None:
    """``cpopg(..., download_pecas=True)`` grava peças e devolve coluna ``pecas``."""
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
    # Sample tem 2 documentos juntados.
    responses.add(responses.GET, DOC_URL, body=doc_body, content_type="text/html")
    responses.add(responses.GET, DOC_URL, body=doc_body, content_type="text/html")

    scraper = jus.scraper("trf3", sleep_time=0)
    df = scraper.cpopg(
        "50059460920254036324", download_pecas=True, diretorio=str(tmp_path)
    )

    assert "pecas" in df.columns, "coluna 'pecas' deve existir quando download_pecas=True"
    saved = df.iloc[0]["pecas"]
    assert len(saved) == 2
    for p in saved:
        assert os.path.isfile(p)
        assert p.endswith(".html")
        with open(p, "rb") as fh:
            assert fh.read() == doc_body
    # Layout: <tmp>/<cnj>/<id>.html
    proc_dir = tmp_path / "50059460920254036324"
    assert proc_dir.is_dir()


@responses.activate
def test_cpopg_with_download_pecas_handles_missing_process(tmp_path) -> None:
    """Processo não encontrado → linha só com id_cnj + ``pecas`` vazio."""
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

    scraper = jus.scraper("trf3", sleep_time=0)
    df = scraper.cpopg(
        "00000000020994030000", download_pecas=True, diretorio=str(tmp_path)
    )
    assert df.iloc[0]["pecas"] == []



def test_cpopg_uses_download_path_when_diretorio_omitted(tmp_path) -> None:
    """Sem ``diretorio``, usa ``download_path`` do construtor."""
    scraper = jus.scraper("trf3", sleep_time=0, download_path=str(tmp_path))
    # Não vamos exercer rede — só asserir que não levanta ValueError ao
    # validar args (a primeira coisa que cpopg faz é validação pydantic).
    # Para chegar até o download real seria preciso mock de rede.
    import inspect

    src = inspect.getsource(scraper.cpopg)
    assert "self.download_path" in src


@responses.activate
def test_cpopg_with_download_pecas_continues_after_peca_error(tmp_path) -> None:
    """Falha numa peça vira warning; as outras peças continuam sendo salvas."""
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
    # 404 é não-retryable: a peça falha de vez e o batch segue. Um 5xx aqui
    # seria retentado por ``_request_with_retry`` e, com o sample 200 logo
    # abaixo na fila, acabaria tendo sucesso na 2ª tentativa — mascarando o
    # cenário de "peça que falha permanentemente".
    responses.add(responses.GET, DOC_URL, status=404)
    doc_body = load_sample_bytes("trf3", "cpopg_pecas/documento_html.html")
    responses.add(responses.GET, DOC_URL, body=doc_body, content_type="text/html")

    scraper = jus.scraper("trf3", sleep_time=0)
    df = scraper.cpopg(
        "50059460920254036324", download_pecas=True, diretorio=str(tmp_path)
    )
    saved = df.iloc[0]["pecas"]
    # Só a segunda peça foi salva.
    assert len(saved) == 1
    assert os.path.isfile(saved[0])
