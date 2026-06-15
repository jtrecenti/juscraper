"""Testes unitarios da extracao de total de paginas TJPR via util compartilhado.

Refs #262: ``extract_total_pages`` migrou para ``extract_count_with_cascade``.
O total vem do link "Ultima Pagina" (``<a class="arrowLastOn">``), cujo href
em JavaScript carrega ``['pageNumber'].value='<total>'``.
"""
from __future__ import annotations

import pytest

from juscraper.courts.tjpr.download import extract_total_pages
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjpr", f"cjsg/{name}")


@pytest.mark.parametrize(
    ("sample_name", "expected"),
    [
        # Formato arrowLastOn / ['pageNumber'].value — total de paginas direto.
        ("results_normal_page_01.html", 39477),
        ("single_page.html", 38767),
        # Sem paginador (zero resultados) — nada casa, assume pagina unica.
        ("no_results.html", 1),
    ],
)
def test_extract_total_pages(sample_name: str, expected: int):
    assert extract_total_pages(_sample(sample_name)) == expected


def test_extract_total_pages_falls_back_to_one_when_unrecognized():
    html = "<div>HTML totalmente diferente sem informacao de paginacao</div>"
    assert extract_total_pages(html) == 1
