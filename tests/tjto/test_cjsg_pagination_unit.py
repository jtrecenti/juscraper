"""Testes unitarios da extracao de contagem TJTO via util compartilhado (refs #87)."""
from __future__ import annotations

from juscraper.courts.tjto.download import _get_total_results
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjto", f"cjsg/{name}")


def test_get_total_results_normal():
    html = _sample("results_normal_page_01.html")
    assert _get_total_results(html) == 70242


def test_get_total_results_single_page():
    html = _sample("single_page.html")
    assert _get_total_results(html) >= 1


def test_get_total_results_no_results_returns_zero():
    html = _sample("no_results.html")
    assert _get_total_results(html) == 0


def test_get_total_results_falls_back_to_resultados_text():
    html = (
        '<html><body><p>pesquisando por <strong>x</strong> - '
        "(123 resultados)</p></body></html>"
    )
    assert _get_total_results(html) == 123


def test_get_total_results_handles_dot_thousands():
    html = (
        '<a class="nav-link active"><span class="num_minuta">'
        "(12.345)</span></a>"
    )
    assert _get_total_results(html) == 12345
