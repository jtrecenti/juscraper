"""Testes unitarios da extracao de contagem TJTO via util compartilhado (refs #87)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from juscraper.courts.tjto.download import _get_total_results, cjsg_download_manager
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjto", f"cjsg/{name}")


def test_get_total_results_normal():
    assert _get_total_results(_sample("results_normal_page_01.html"), "1") == 70242


def test_get_total_results_single_page():
    assert _get_total_results(_sample("single_page.html"), "1") == 9


def test_get_total_results_no_results_returns_zero():
    assert _get_total_results(_sample("no_results.html"), "1") == 0


def test_get_total_results_pagina_alem_do_total_traz_o_total_da_busca():
    """A página 3 de uma busca de 9 resultados diz "Nenhum documento encontrado", mas a aba traz 9."""
    assert _get_total_results(_sample("pagina_alem_do_total.html"), "1") == 9


@pytest.mark.parametrize(("sample", "type_minuta", "total"), [
    ("cjsg/decisoes_single_page.html", "2", 3),
    ("cjpg/sentencas_page_01.html", "3", 1284),
])
def test_get_total_results_le_a_aba_do_tipo_pedido_mesmo_sem_active(sample, type_minuta, total):
    """O total vem da aba do tipo pedido, sem depender da classe ``active`` (capturas de 26/11/2026).

    As outras abas trazem outros totais: (9) e (0) em decisões, (14) e (1.741) em
    sentenças. Sem ``active``, ler o primeiro "(N)" da página daria 9 em decisões.
    """
    html = load_sample("tjto", sample).replace("nav-link active", "nav-link")
    assert "nav-link active" not in html
    assert _get_total_results(html, type_minuta) == total


def test_get_total_results_sem_a_aba_nao_le_outra_contagem():
    """Sem a aba pedida nem o "(N resultados)", não há contagem, e não a de outra aba."""
    html = _sample("decisoes_single_page.html").replace('type_minuta="2"', "")
    assert _get_total_results(html, "2") is None


def test_get_total_results_falls_back_to_resultados_text():
    html = (
        '<html><body><p>pesquisando por <strong>x</strong> - '
        "(123 resultados)</p></body></html>"
    )
    assert _get_total_results(html, "1") == 123


def test_get_total_results_handles_dot_thousands():
    html = (
        '<li type_minuta="1"><a class="nav-link"><span class="num_minuta">'
        "(12.345)</span></a></li>"
    )
    assert _get_total_results(html, "1") == 12345


def test_download_sem_contagem_levanta_em_vez_de_parar_na_pagina_1():
    """Sem a contagem, o download levanta ``ValueError`` (``resolve_total_pages``), como no TJPI."""
    html = _sample("decisoes_single_page.html").replace('type_minuta="2"', "")

    def request_fn(_metodo, _url, **_kwargs):
        return SimpleNamespace(text=html)

    with pytest.raises(ValueError, match="TJTO: a página lida não traz a contagem"):
        cjsg_download_manager("x", request_fn=request_fn, sleep_time=0, type_minuta="2")
