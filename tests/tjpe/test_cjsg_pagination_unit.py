"""Testes unitarios da parseria de paginacao TJPE (refs #87)."""
from __future__ import annotations

from juscraper.courts.tjpe.download import extract_total_docs, is_escolha_page, is_results_page
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjpe", f"cjsg/{name}")


def test_extract_total_docs_resultado_normal():
    assert extract_total_docs(_sample("step_03_resultado.html")) == 953


def test_extract_total_docs_simples_resultado():
    assert extract_total_docs(_sample("simples_resultado.html")) == 988


def test_extract_total_docs_escolha_page_fallback():
    assert extract_total_docs(_sample("step_02_escolha.html")) == 953


def test_extract_total_docs_no_results_returns_zero():
    assert extract_total_docs(_sample("no_results.html")) == 0


def test_extract_total_docs_resilient_to_table_class_change():
    html = (
        '<div class="painel-novo">'
        "<span>Documentos encontrados: 1234</span></div>"
    )
    assert extract_total_docs(html) == 1234


def test_extract_total_docs_falls_back_to_zero_when_unrecognized():
    html = "<div>HTML totalmente diferente sem informacao de contagem</div>"
    assert extract_total_docs(html) == 0


def test_is_results_page_case_insensitive():
    html = "<html><body>DOCUMENTOS ENCONTRADOS: 5<br>DOCUMENTO 1</body></html>"
    assert is_results_page(html) is True


def test_is_escolha_page_case_insensitive():
    html = "<html><body>5 DOCUMENTOS ENCONTRADOS</body></html>"
    assert is_escolha_page(html) is True
    assert is_results_page(html) is False
