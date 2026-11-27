"""Testes unitarios da extracao de contagem TJTO via util compartilhado (refs #87)."""
from __future__ import annotations

import pytest

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


def test_get_total_results_pagina_alem_do_total_traz_o_total_da_busca():
    """A página 3 de uma busca de 9 resultados diz "Nenhum documento encontrado", mas a aba traz 9."""
    assert _get_total_results(_sample("pagina_alem_do_total.html")) == 9


@pytest.mark.parametrize(("sample", "total"), [
    ("cjsg/decisoes_single_page.html", 3),
    ("cjpg/sentencas_page_01.html", 1284),
])
def test_get_total_results_le_a_aba_do_tipo_pedido(sample, total):
    """Fora de acórdãos, o portal marca ``active`` na aba do tipo pedido (capturas de 26/11/2026).

    As outras abas trazem outros totais: (9) e (0) em decisões, (14) e (1.741) em
    sentenças. Ler a aba de acórdãos daria 9 e 14.
    """
    assert _get_total_results(load_sample("tjto", sample)) == total


def test_get_total_results_sem_a_aba_ativa_nao_le_o_html_bruto():
    """Sem a aba ativa, um número entre parênteses no texto da página (ano numa ementa) não vira total."""
    html = (
        '<html><body><p>pesquisando por <strong>x</strong> - '
        "(123 resultados)</p><p>Lei n. 8.112 (1990)</p></body></html>"
    )
    assert _get_total_results(html) == 0


def test_get_total_results_handles_dot_thousands():
    html = (
        '<a class="nav-link active"><span class="num_minuta">'
        "(12.345)</span></a>"
    )
    assert _get_total_results(html) == 12345
