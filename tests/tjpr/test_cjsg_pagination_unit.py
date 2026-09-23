"""Testes unitarios da extracao de total de paginas TJPR.

O total vem do link "Última Página" (``<a class="arrowLastOn">``) do
paginador ``#navigator .navRight``, cujo href em JavaScript carrega
``['pageNumber'].value='<total>'``. Os casos de erro partem dos samples
reais e trocam só o link "Última" (ou o ``pageNumber`` dele), para que o
resto do paginador continue exatamente como o portal o desenha.
"""
from __future__ import annotations

import re

import pytest

from juscraper.courts.tjpr.download import extract_total_pages
from tests._helpers import load_sample

_LINK_ULTIMA_RE = re.compile(r'<a class="arrowLastOn"[^>]*>.*?</a>')
_PAGE_NUMBER_ULTIMA = "['pageNumber'].value='39477'"


def _sample(name: str) -> str:
    return load_sample("tjpr", f"cjsg/{name}")


def _pagina_1() -> str:
    """Primeira página real, com os dois paginadores (acima e abaixo da lista)."""
    html = _sample("results_normal_page_01.html")
    assert len(_LINK_ULTIMA_RE.findall(html)) == 2
    assert html.count(_PAGE_NUMBER_ULTIMA) == 2
    return html


def _ancora_desativada() -> str:
    """Âncora "Última" desativada, copiada do sample real de página única."""
    match = re.search(r'<a class="arrowLastOff"[^>]*>.*?</a>', _sample("single_page.html"))
    assert match is not None
    return match.group(0)


def _ultima_desativada(html: str) -> str:
    """Troca só o primeiro link "Última" ativo (paginador de cima) pela âncora desativada."""
    desativado = _ancora_desativada()
    return _LINK_ULTIMA_RE.sub(lambda _: desativado, html, count=1)


def _acrescenta_depois_da_ultima(html: str, extra) -> str:
    """Em cada paginador, acrescenta ``extra(link)`` logo depois do link "Última" ativo."""
    return _LINK_ULTIMA_RE.sub(lambda m: m.group(0) + extra(m.group(0)), html)


@pytest.mark.parametrize(
    ("sample_name", "expected"),
    [
        # Link "Última" ativo nos dois paginadores, com o mesmo total.
        ("results_normal_page_01.html", 39477),
        ("results_normal_page_02.html", 39477),
        # Zero resultados: o #navigator existe, mas o .navRight vem vazio.
        ("no_results.html", 1),
    ],
)
def test_extract_total_pages(sample_name: str, expected: int):
    assert extract_total_pages(_sample(sample_name)) == expected


def test_extract_total_pages_pagina_unica_real_devolve_um():
    """Busca real de página única: os dois paginadores trazem "Última" desativada, sem href."""
    html = _sample("single_page.html")
    assert "arrowLastOn" not in html
    assert html.count('class="arrowLastOff"') == 2
    assert extract_total_pages(html) == 1


def test_extract_total_pages_dois_links_ultima_iguais_no_mesmo_paginador():
    """Link "Última" repetido com o mesmo total no mesmo paginador não é ambíguo."""
    html = _acrescenta_depois_da_ultima(_pagina_1(), lambda link: link)
    assert html.count(_PAGE_NUMBER_ULTIMA) == 4
    assert extract_total_pages(html) == 39477


def test_extract_total_pages_sem_paginador_devolve_um():
    html = "<div>HTML totalmente diferente sem informacao de paginacao</div>"
    assert extract_total_pages(html) == 1


@pytest.mark.parametrize(
    ("variante", "mensagem"),
    [
        pytest.param(
            lambda html: _LINK_ULTIMA_RE.sub("", html),
            "sem o link de última página",
            id="sem-link-ultima",
        ),
        pytest.param(
            lambda html: html.replace("document.forms['pesquisaForm']" + _PAGE_NUMBER_ULTIMA + ";", ""),
            "pageNumber válido",
            id="ultima-sem-pageNumber",
        ),
        pytest.param(
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='ultima'"),
            "pageNumber válido",
            id="pageNumber-nao-numerico",
        ),
        pytest.param(
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='0'"),
            "pageNumber válido",
            id="pageNumber-zero",
        ),
        pytest.param(
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='39476'", 1),
            "discordam do total",
            id="paginadores-discordam",
        ),
        pytest.param(
            _ultima_desativada,
            "discordam do total",
            id="um-ativo-outro-desativado",
        ),
        pytest.param(
            # O segundo link vem depois do primeiro nos dois paginadores, que
            # continuam iguais entre si: só a checagem dentro do paginador pega.
            lambda html: _acrescenta_depois_da_ultima(html, lambda link: link.replace("'39477'", "'39476'")),
            "discordam do total",
            id="dois-ativos-discordantes-no-mesmo-paginador",
        ),
        pytest.param(
            lambda html: _acrescenta_depois_da_ultima(html, lambda _: _ancora_desativada()),
            "ativo .* e desativado",
            id="ativo-e-desativado-no-mesmo-paginador",
        ),
    ],
)
def test_extract_total_pages_levanta_quando_nao_le_o_total(variante, mensagem: str):
    """Paginador presente sem total legível e coerente: levanta em vez de estimar."""
    with pytest.raises(ValueError, match=mensagem):
        extract_total_pages(variante(_pagina_1()))


def test_extract_total_pages_sem_link_ultima_na_pagina_2_levanta():
    """Na página 2 o maior ``pageNumber`` visível seria 4, não o total."""
    html = _LINK_ULTIMA_RE.sub("", _sample("results_normal_page_02.html"))
    with pytest.raises(ValueError, match="sem o link de última página"):
        extract_total_pages(html)
