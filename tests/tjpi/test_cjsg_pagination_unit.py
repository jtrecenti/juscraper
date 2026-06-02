"""Testes unitarios da extracao de contagem TJPI via util compartilhado (refs #87)."""
from __future__ import annotations

from juscraper.courts.tjpi.download import _get_total_pages
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjpi", f"cjsg/{name}")


def test_get_total_pages_results_normal():
    html = _sample("results_normal_page_01.html")
    assert _get_total_pages(html) == 5515


def test_get_total_pages_single_page_returns_one():
    html = _sample("single_page.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_no_results_returns_one():
    html = _sample("no_results.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_resilient_to_alternate_pagination_class():
    html = (
        '<nav><ul class="pagination">'
        '<li><a href="?page=1">1</a></li>'
        '<li><a href="?page=99&q=teste">99</a></li>'
        "</ul></nav>"
    )
    assert _get_total_pages(html) == 99


def test_get_total_pages_falls_back_when_pagination_missing():
    html = "<html><body><p>conteudo sem paginacao</p></body></html>"
    assert _get_total_pages(html) == 1
