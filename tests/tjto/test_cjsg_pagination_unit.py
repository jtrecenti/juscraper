"""Testes unitarios da extracao de contagem TJTO via util compartilhado (refs #87)."""
from __future__ import annotations

import logging

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


_POR_TIPO = [
    ("cjsg/decisoes_single_page.html", "2", 3),
    ("cjpg/sentencas_page_01.html", "3", 1284),
]


@pytest.mark.parametrize(("sample", "type_minuta", "total"), _POR_TIPO)
def test_get_total_results_le_a_aba_do_tipo_pedido(sample, type_minuta, total):
    """Fora de acórdãos, a contagem vem da aba do tipo pedido (capturas de 26/11/2026).

    As outras abas trazem outros totais: (9) e (0) em decisões, (14) e (1.741) em
    sentenças. Ler a aba de acórdãos daria 9 e 14.
    """
    assert _get_total_results(load_sample("tjto", sample), type_minuta) == total


@pytest.mark.parametrize(("sample", "type_minuta", "total"), _POR_TIPO)
def test_get_total_results_sem_active_ainda_le_a_aba_do_tipo_pedido(sample, type_minuta, total):
    """Se o portal deixar de marcar ``active``, o total não pode vir da aba de acórdãos.

    Antes, a regex do "(N)" rodava também no HTML bruto e pegava o primeiro da
    página: 9 em vez de 3 em decisões, 14 em vez de 1.284 em sentenças.
    """
    html = load_sample("tjto", sample).replace("nav-link active", "nav-link")
    assert "nav-link active" not in html
    assert _get_total_results(html, type_minuta) == total


def test_get_total_results_sem_a_aba_avisa_e_nao_le_outra_contagem(caplog):
    """Sem a aba pedida nem o "(N resultados)", avisa e devolve 0 (só a 1ª página)."""
    html = load_sample("tjto", "cjsg/decisoes_single_page.html").replace('type_minuta="2"', "")
    with caplog.at_level(logging.WARNING, logger="juscraper.tjto"):
        assert _get_total_results(html, "2") == 0
    assert "type_minuta=2" in caplog.text


def test_get_total_results_falls_back_to_resultados_text():
    html = (
        '<html><body><p>pesquisando por <strong>x</strong> - '
        "(123 resultados)</p></body></html>"
    )
    assert _get_total_results(html) == 123


def test_get_total_results_handles_dot_thousands():
    html = (
        '<li type_minuta="1"><a class="nav-link"><span class="num_minuta">'
        "(12.345)</span></a></li>"
    )
    assert _get_total_results(html) == 12345
