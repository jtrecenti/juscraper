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


def _ultima_desativada(html: str, count: int = 0) -> str:
    """Troca o link "Última" ativo pela forma desativada.

    A forma segue a que o portal usa para "Primeira" e "Anterior" na
    página 1 (``arrowFirstOff``/``arrowPreviousOff``: mesma âncora, sem
    ``href``). Não há sample real da última página para confirmar.
    """
    desativado = (
        '<a class="arrowLastOff" title="Ir para a &uacute;ltima p&aacute;gina">'
        "<span>&Uacute;ltima P&aacute;gina</span></a>"
    )
    return _LINK_ULTIMA_RE.sub(desativado, html, count=count)


def _pagina_unica() -> str:
    """Página 1 de uma busca de página única: sem links numerados, próxima e última desativadas."""
    html = re.sub(r',&nbsp;<a title="Ir para a p&aacute;gina \d+" href="[^"]*">\d+</a>', "", _pagina_1())
    html = re.sub(
        r'<a class="arrowNextOn"[^>]*>(.*?)</a>',
        r'<a class="arrowNextOff" title="Ir para a pr&oacute;xima p&aacute;gina">\1</a>',
        html,
    )
    return _ultima_desativada(html)


@pytest.mark.parametrize(
    ("sample_name", "expected"),
    [
        # Link "Última" ativo nos dois paginadores, com o mesmo total.
        ("results_normal_page_01.html", 39477),
        ("results_normal_page_02.html", 39477),
        # Apesar do nome, este sample tem 38767 páginas (o paginador aponta a última).
        ("single_page.html", 38767),
        # Zero resultados: o #navigator existe, mas o .navRight vem vazio.
        ("no_results.html", 1),
    ],
)
def test_extract_total_pages(sample_name: str, expected: int):
    assert extract_total_pages(_sample(sample_name)) == expected


def test_extract_total_pages_sem_paginador_devolve_um():
    html = "<div>HTML totalmente diferente sem informacao de paginacao</div>"
    assert extract_total_pages(html) == 1


def test_extract_total_pages_ultima_desativada_na_pagina_1_devolve_um():
    """Na página 1, "Última" desativada significa que a página 1 é a última."""
    html = _pagina_unica()
    assert "arrowLastOn" not in html
    assert html.count("arrowLastOff") == 2
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
            "paginadores discordam",
            id="paginadores-discordam",
        ),
        pytest.param(
            lambda html: _ultima_desativada(html, count=1),
            "paginadores discordam",
            id="um-ativo-outro-desativado",
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
