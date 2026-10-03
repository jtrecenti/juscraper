"""Testes unitários da contagem de páginas do TJPI.

O total vem da contagem "de um total de N jurisprudência(s)" (ou "Exibindo N
jurisprudência(s)" em página única), dividida pelas 25 linhas por página, e
os links de última página (``»``) da página inteira são conferidos contra
ela. Os casos sintéticos partem do sample real e mudam só o trecho em teste.
"""
from __future__ import annotations

import pytest

from juscraper.courts.tjpi.download import _get_total_pages
from tests._helpers import load_sample

# Link de última página exatamente como aparece no sample real da busca
# "dano moral": 137865 resultados em páginas de 25 dão 5515 páginas.
_LINK_ULTIMA = '<a class="page-link" href="/jurisprudences/search?page=5515&amp;q=dano+moral">&raquo;</a>'
_CONTAGEM = "de um total de <b>137865</b> jurisprudência(s)"


def _sample(name: str) -> str:
    return load_sample("tjpi", f"cjsg/{name}")


def _link_ultima(page: str) -> str:
    return f'<a class="page-link" href="/jurisprudences/search?page={page}&amp;q=dano+moral">&raquo;</a>'


def _primeira_pagina() -> str:
    html = _sample("results_normal_page_01.html")
    assert html.count(_LINK_ULTIMA) == 2
    assert html.count(_CONTAGEM) == 2
    return html


def _primeira_pagina_com(substituto: str, vezes: int = -1) -> str:
    """Troca o link ``»`` do sample real; ``vezes=1`` só no paginador de cima."""
    return _primeira_pagina().replace(_LINK_ULTIMA, substituto, vezes)


@pytest.mark.parametrize(
    ("sample_name", "expected"),
    [
        ("results_normal_page_01.html", 5515),
        # Na página 2 o paginador ganha « e ‹ (sem ``page=``); total igual.
        ("results_normal_page_02.html", 5515),
        # "Exibindo 5 jurisprudência(s)", sem paginador.
        ("single_page.html", 1),
        # "Sem resultados para: ...".
        ("no_results.html", 1),
    ],
)
def test_get_total_pages_samples(sample_name: str, expected: int):
    assert _get_total_pages(_sample(sample_name)) == expected


@pytest.mark.parametrize(
    "variante",
    [
        pytest.param(lambda html: html.replace('class="pagination', 'class="pager'), id="ul-pagination-renomeado"),
        pytest.param(
            # Tema padrão do Kaminari: o » vem como "Last »" dentro de span.last.
            lambda html: html.replace(
                _LINK_ULTIMA,
                '<span class="last"><a href="/jurisprudences/search?page=5515&amp;q=dano+moral">'
                "Last &raquo;</a></span>",
            ),
            id="tema-kaminari",
        ),
        pytest.param(lambda html: html.replace(_LINK_ULTIMA, ""), id="sem-link-ultima"),
        pytest.param(lambda html: html.replace(_LINK_ULTIMA, "", 1), id="um-paginador-sem-link-ultima"),
        pytest.param(lambda html: html.replace('class="pb-3"', 'class="mb-3"'), id="div-da-contagem-renomeado"),
        pytest.param(
            lambda html: html.replace(_LINK_ULTIMA, _LINK_ULTIMA.replace("&raquo;", "\n  &raquo; \n")),
            id="espaco-em-volta-do-link",
        ),
        pytest.param(lambda html: html.replace(_LINK_ULTIMA, _LINK_ULTIMA + _LINK_ULTIMA), id="dois-links-iguais"),
        pytest.param(lambda html: html.replace("137865", "137.865"), id="contagem-com-separador-de-milhar"),
    ],
)
def test_get_total_pages_markup_alterado_continua_lendo_a_contagem(variante):
    """Paginador renomeado ou » sumido não pode virar 1: a contagem continua na página."""
    assert _get_total_pages(variante(_primeira_pagina())) == 5515


@pytest.mark.parametrize(
    ("html", "mensagem"),
    [
        pytest.param(lambda: _primeira_pagina_com(_link_ultima("7"), 1), r"aponta \[7\]", id="paginadores-discordam"),
        pytest.param(
            # O primeiro » de cada paginador traz 5515; o segundo, com 7, tem que pesar.
            lambda: _primeira_pagina_com(_LINK_ULTIMA + _link_ultima("7")),
            r"aponta \[7\]",
            id="dois-links-discordantes-no-mesmo-paginador",
        ),
        pytest.param(
            # » com page=1 e › apontando para a página 2: markup inconsistente.
            lambda: _primeira_pagina_com(_link_ultima("1")),
            r"aponta \[1\]",
            id="link-ultima-com-page-1",
        ),
        pytest.param(
            lambda: _primeira_pagina_com('<a class="page-link" href="/jurisprudences/search?q=dano+moral">&raquo;</a>'),
            "número de página válido",
            id="link-ultima-sem-page",
        ),
        pytest.param(lambda: _primeira_pagina_com(_link_ultima("0")), "número de página válido", id="page-zero"),
        pytest.param(lambda: _primeira_pagina_com(_link_ultima("²")), "número de página válido", id="digito-unicode"),
        pytest.param(
            lambda: _primeira_pagina_com(_link_ultima("５５１５")),
            "número de página válido",
            id="digitos-largura-total",
        ),
        pytest.param(
            lambda: _primeira_pagina().replace(_CONTAGEM, ""),
            "não traz a contagem",
            id="sem-contagem",
        ),
        pytest.param(
            lambda: _primeira_pagina().replace(_CONTAGEM, "").replace('class="pagination', 'class="pager'),
            "não traz a contagem",
            id="sem-contagem-e-paginador-renomeado",
        ),
        pytest.param(
            lambda: "<html><body><p>conteudo sem paginacao</p></body></html>",
            "não traz a contagem",
            id="pagina-sem-contagem-nem-paginador",
        ),
    ],
)
def test_get_total_pages_levanta_quando_nao_fixa_o_total(html, mensagem: str):
    """Sem contagem, ou com » que não bate com ela: levanta em vez de estimar."""
    with pytest.raises(ValueError, match=mensagem):
        _get_total_pages(html())


def test_get_total_pages_ementa_com_total_de_n_nao_vira_contagem():
    """Sem o rótulo, "de um total de 84 prestações" numa ementa não conta como resultado."""
    html = _primeira_pagina().replace(_CONTAGEM, "").replace("</body>", "<p>de um total de 84 prestações</p></body>")
    with pytest.raises(ValueError, match="não traz a contagem"):
        _get_total_pages(html)
