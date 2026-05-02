"""Testes unitarios da extracao de contagem TJSC via util compartilhado (refs #87)."""
from __future__ import annotations

from juscraper.courts.tjsc.download import RESULTS_PER_PAGE, _get_total_pages
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjsc", f"cjsg/{name}", encoding="latin-1")


def test_get_total_pages_results_normal():
    html = _sample("results_normal_page_01.html")
    total_docs = 218319
    expected = max(1, (total_docs + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
    assert _get_total_pages(html) == expected


def test_get_total_pages_single_page():
    html = _sample("single_page.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_no_results_returns_one():
    html = _sample("no_results.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_resilient_to_h2_class_change():
    html = '<div><h2 class="qualquer-classe">75 documentos encontrados</h2></div>'
    assert _get_total_pages(html) == max(
        1, (75 + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    )


def test_get_total_pages_falls_back_to_one_when_unrecognized():
    html = "<div>HTML totalmente diferente sem informacao de contagem</div>"
    assert _get_total_pages(html) == 1
