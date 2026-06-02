"""Testes unitarios da extracao de contagem TJGO via util compartilhado (refs #87)."""
from __future__ import annotations

from juscraper.courts.tjgo.download import _extract_total
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjgo", f"cjsg/{name}", encoding="iso-8859-1")


def test_extract_total_results_normal_first_page():
    html = _sample("results_normal_page_01.html")
    assert _extract_total(html) == 1273234


def test_extract_total_single_page():
    html = _sample("single_page.html")
    assert _extract_total(html) == 1


def test_extract_total_no_results_falls_back_to_zero():
    html = _sample("no_results.html")
    assert _extract_total(html) == 0


def test_extract_total_handles_dot_separated_thousands():
    html = (
        '<legend class="formLocalizarLegenda">'
        "1.234 resultados encontrados para o filtro da pesquisa"
        "</legend>"
    )
    assert _extract_total(html) == 1234


def test_extract_total_resilient_to_legend_class_change():
    html = (
        '<div class="painel-resultados">'
        "<span>456 resultados encontrados</span></div>"
    )
    assert _extract_total(html) == 456
