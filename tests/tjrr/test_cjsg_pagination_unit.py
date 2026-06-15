"""Testes unitarios da extracao de contagem TJRR via util compartilhado (refs #87)."""
from __future__ import annotations

from juscraper.courts.tjrr.download import _get_total_pages
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjrr", f"cjsg/{name}")


def test_get_total_pages_results_normal():
    html = _sample("step_02_search.html")
    assert _get_total_pages(html) == 1210


def test_get_total_pages_single_page_sample():
    html = _sample("single_page.html")
    assert _get_total_pages(html) == 58


def test_get_total_pages_no_results_sample():
    html = _sample("no_results.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_falls_back_to_one_without_paginator():
    assert _get_total_pages("<html><body>nada de paginator</body></html>") == 1


def test_get_total_pages_resilient_to_class_change():
    html = (
        '<div class="paginator"><span class="paginator-status">'
        "(1 of 99)</span></div>"
    )
    assert _get_total_pages(html) == 99
