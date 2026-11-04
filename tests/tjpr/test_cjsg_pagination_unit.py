"""Testes unitarios da extracao de total de paginas TJPR.

O total vem da contagem "N registro(s) encontrado(s)" do ``.navLeft``,
dividida pelas 50 linhas por pagina, e o link "Última Página"
(``a.arrowLastOn``, com ``['pageNumber'].value='<total>'`` no href, ou
``a.arrowLastOff`` desativado) e conferido contra ela. Os casos partem dos
samples reais e trocam so o trecho em teste, para que o resto da pagina
continue exatamente como o portal o desenha.
"""
from __future__ import annotations

import re

import pytest

from juscraper.courts.tjpr.download import extract_total_pages
from tests._helpers import load_sample

_LINK_ULTIMA_RE = re.compile(r'<a class="arrowLastOn"[^>]*>.*?</a>')
_LINK_PROXIMA_RE = re.compile(r'<a class="arrowNextOn"[^>]*>.*?</a>')
_PAGE_NUMBER_ULTIMA = "['pageNumber'].value='8213'"
# 410614 registros em paginas de 50: 8213 paginas, o mesmo total do link.
_CONTAGEM = "410614 registro(s) encontrado(s)"
_TOTAL = 8213


def _sample(name: str) -> str:
    return load_sample("tjpr", f"cjsg/{name}")


def _pagina_1() -> str:
    """Primeira pagina real, com os dois paginadores (acima e abaixo da lista)."""
    html = _sample("results_normal_page_01.html")
    assert len(_LINK_ULTIMA_RE.findall(html)) == 2
    assert html.count(_PAGE_NUMBER_ULTIMA) == 2
    assert html.count(_CONTAGEM) == 2
    return html


def _ancora(classe: str) -> str:
    """Âncora desativada (``arrowLastOff``/``arrowNextOff``) copiada do sample real de pagina unica."""
    match = re.search(rf'<a class="{classe}"[^>]*>.*?</a>', _sample("single_page.html"))
    assert match is not None
    return match.group(0)


def _acrescenta_depois_da_ultima(html: str, extra) -> str:
    """Em cada paginador, acrescenta ``extra(link)`` logo depois do link "Última" ativo."""
    return _LINK_ULTIMA_RE.sub(lambda m: m.group(0) + extra(m.group(0)), html)


def _sem_contagem(html: str) -> str:
    html = re.sub(r"[0-9]+ registro\(s\) encontrado\(s\)", "", html)
    assert "registro(s) encontrado(s)" not in html
    return html


@pytest.mark.parametrize(
    ("sample_name", "expected"),
    [
        ("results_normal_page_01.html", _TOTAL),
        ("results_normal_page_02.html", _TOTAL),
        # "0 registro(s) encontrado(s)" e o .navRight vazio.
        ("no_results.html", 1),
    ],
)
def test_extract_total_pages(sample_name: str, expected: int):
    assert extract_total_pages(_sample(sample_name)) == expected


def test_extract_total_pages_pagina_unica_real_devolve_um():
    """Busca real com 6 resultados: os dois paginadores trazem "Última" desativada, sem href."""
    html = _sample("single_page.html")
    assert "arrowLastOn" not in html
    assert html.count('class="arrowLastOff"') == 2
    assert extract_total_pages(html) == 1


def test_extract_total_pages_dois_links_ultima_iguais_no_mesmo_paginador():
    html = _acrescenta_depois_da_ultima(_pagina_1(), lambda link: link)
    assert html.count(_PAGE_NUMBER_ULTIMA) == 4
    assert extract_total_pages(html) == _TOTAL


@pytest.mark.parametrize(
    "variante",
    [
        pytest.param(lambda html: html.replace('id="navigator"', 'id="navegador"'), id="navigator-renomeado"),
        pytest.param(lambda html: html.replace('class="navRight"', 'class="nav-right"'), id="navRight-renomeado"),
        pytest.param(lambda html: html.replace('class="navLeft"', 'class="nav-left"'), id="navLeft-renomeado"),
        pytest.param(lambda html: _LINK_ULTIMA_RE.sub("", html), id="sem-link-ultima"),
        pytest.param(
            # Paginador so de texto, sem nenhuma tag filha.
            lambda html: re.sub(
                r'<div class="navRight">.*?</div>', f'<div class="navRight">Página 1 de {_TOTAL}</div>', html
            ),
            id="navRight-so-texto",
        ),
        pytest.param(
            lambda html: re.sub(r'<div class="navRight">.*?</div>', '<div class="navRight"></div>', html, count=1),
            id="um-navRight-vazio",
        ),
    ],
)
def test_extract_total_pages_markup_alterado_continua_lendo_a_contagem(variante):
    """Contêiner renomeado ou link sumido nao pode virar 1: a contagem continua na pagina."""
    assert extract_total_pages(variante(_pagina_1())) == _TOTAL


def test_extract_total_pages_link_ultima_fora_do_navigator_ainda_e_conferido():
    """Com o contêiner renomeado, um link "Última" divergente continua pego."""
    html = _pagina_1().replace('id="navigator"', 'id="navegador"')
    html = html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='7'")
    with pytest.raises(ValueError, match=r"aponta \[7\]"):
        extract_total_pages(html)


@pytest.mark.parametrize(
    ("variante", "mensagem"),
    [
        pytest.param(_sem_contagem, "não traz a contagem", id="sem-contagem"),
        pytest.param(
            lambda html: _sem_contagem(html.replace('id="navigator"', 'id="navegador"')),
            "não traz a contagem",
            id="sem-contagem-e-contêiner-renomeado",
        ),
        pytest.param(
            lambda html: html.replace("document.forms['pesquisaForm']" + _PAGE_NUMBER_ULTIMA + ";", ""),
            "número de página válido",
            id="ultima-sem-pageNumber",
        ),
        pytest.param(
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='ultima'"),
            "número de página válido",
            id="pageNumber-nao-numerico",
        ),
        pytest.param(
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='0'"),
            "número de página válido",
            id="pageNumber-zero",
        ),
        pytest.param(
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='８２１３'"),
            "número de página válido",
            id="pageNumber-digitos-largura-total",
        ),
        pytest.param(
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='8212'", 1),
            r"aponta \[8212\]",
            id="paginadores-discordam",
        ),
        pytest.param(
            # Com ``pageSize=10`` no payload, o portal desenha o link com 5x
            # mais paginas do que as 50 linhas por pagina comportam.
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='41062'"),
            r"aponta \[41062\]",
            id="link-calculado-com-pageSize-10",
        ),
        pytest.param(
            lambda html: html.replace(_PAGE_NUMBER_ULTIMA, "['pageNumber'].value='1'"),
            r"aponta \[1\]",
            id="ultima-ativa-com-pageNumber-1",
        ),
        pytest.param(
            lambda html: _LINK_ULTIMA_RE.sub(lambda _: _ancora("arrowLastOff"), html, count=1),
            r"aponta \[1\]",
            id="um-ativo-outro-desativado",
        ),
        pytest.param(
            # "Última" desativada nos dois paginadores, "Próxima" ainda ativa.
            lambda html: _LINK_ULTIMA_RE.sub(lambda _: _ancora("arrowLastOff"), html),
            r"aponta \[1\]",
            id="ultima-desativada-com-proxima-ativa",
        ),
        pytest.param(
            lambda html: _acrescenta_depois_da_ultima(html, lambda link: link.replace("'8213'", "'8212'")),
            r"aponta \[8212\]",
            id="dois-ativos-discordantes-no-mesmo-paginador",
        ),
    ],
)
def test_extract_total_pages_levanta_quando_nao_fixa_o_total(variante, mensagem: str):
    """Sem contagem, ou com link que nao bate com ela: levanta em vez de estimar."""
    with pytest.raises(ValueError, match=mensagem):
        extract_total_pages(variante(_pagina_1()))


def test_extract_total_pages_html_sem_contagem_nem_paginador_levanta():
    """Pagina de erro ou markup novo: antes virava 1 pagina em silencio."""
    with pytest.raises(ValueError, match="não traz a contagem"):
        extract_total_pages("<div>HTML totalmente diferente sem informacao de paginacao</div>")


def test_extract_total_pages_pagina_unica_com_contagem_de_varias_paginas_levanta():
    """Com "Última" e "Próxima" desativadas, uma contagem acima de 50 é contraditória."""
    html = _sample("single_page.html").replace("6 registro(s) encontrado(s)", "60 registro(s) encontrado(s)")
    assert _LINK_PROXIMA_RE.search(html) is None
    with pytest.raises(ValueError, match=r"aponta \[1\]"):
        extract_total_pages(html)
