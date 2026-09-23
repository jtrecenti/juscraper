"""Testes unitarios da contagem de paginas do TJPI.

O total vem do link de ultima pagina (``»``) dos paginadores
``ul.pagination`` (o TJPI desenha dois, acima e abaixo da lista). Um formato
por teste: sem paginador (pagina unica ou zero resultados), paginador com
``»``, e os estados ambiguos que levantam ``ValueError``: paginador sem
``»``, ``»`` sem ``page=N`` e paginadores que discordam do total. Os casos
sinteticos partem do sample real e mudam so o link ``»``.
"""
from __future__ import annotations

import pytest

from juscraper.courts.tjpi.download import _get_total_pages
from tests._helpers import load_sample

# Link de ultima pagina exatamente como aparece no sample real da busca
# "dano moral" (5515 paginas).
_LINK_ULTIMA = '<a class="page-link" href="/jurisprudences/search?page=5515&amp;q=dano+moral">&raquo;</a>'


def _sample(name: str) -> str:
    return load_sample("tjpi", f"cjsg/{name}")


def _primeira_pagina_com(substituto: str, vezes: int = -1) -> str:
    """Troca o link ``»`` do sample real; ``vezes=1`` so no paginador de cima."""
    html = _sample("results_normal_page_01.html")
    assert html.count(_LINK_ULTIMA) == 2
    return html.replace(_LINK_ULTIMA, substituto, vezes)


def test_get_total_pages_results_normal():
    html = _sample("results_normal_page_01.html")
    assert _get_total_pages(html) == 5515


def test_get_total_pages_segunda_pagina_le_o_mesmo_total():
    # Na pagina 2 o paginador ganha os links de primeira e anterior
    # (« e ‹, sem ``page=``); o total continua no ».
    html = _sample("results_normal_page_02.html")
    assert _get_total_pages(html) == 5515


def test_get_total_pages_single_page_returns_one():
    html = _sample("single_page.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_no_results_returns_one():
    html = _sample("no_results.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_falls_back_when_pagination_missing():
    html = "<html><body><p>conteudo sem paginacao</p></body></html>"
    assert _get_total_pages(html) == 1


def test_get_total_pages_sem_paginador_ignora_page_fora_dele():
    # ``page=N`` fora do ``ul.pagination`` nao e contagem de paginas.
    html = _sample("single_page.html").replace(
        "</body>", '<a href="/jurisprudences/search?page=42&amp;q=x">42</a></body>'
    )
    assert _get_total_pages(html) == 1


def test_get_total_pages_paginadores_que_discordam_levantam():
    # O maior ``page=N`` (5515, do paginador de baixo) nao desempata: os
    # dois paginadores saem do mesmo helper, e divergencia e markup quebrado.
    html = _primeira_pagina_com(
        '<a class="page-link" href="/jurisprudences/search?page=7&amp;q=dano+moral">&raquo;</a>', 1
    )
    with pytest.raises(ValueError, match="discordam"):
        _get_total_pages(html)


def test_get_total_pages_um_paginador_sem_link_de_ultima_levanta():
    html = _primeira_pagina_com("", 1)
    with pytest.raises(ValueError, match="última página"):
        _get_total_pages(html)


def test_get_total_pages_paginador_sem_link_de_ultima_levanta():
    # Sem o », o maior ``page=N`` visivel e o da janela (aqui, 2), e nao o
    # total. Estimar baixaria menos paginas em silencio.
    html = _primeira_pagina_com("")
    with pytest.raises(ValueError, match="última página"):
        _get_total_pages(html)


def test_get_total_pages_link_de_ultima_sem_page_levanta():
    html = _primeira_pagina_com(
        '<a class="page-link" href="/jurisprudences/search?q=dano+moral">&raquo;</a>'
    )
    with pytest.raises(ValueError, match="page="):
        _get_total_pages(html)


def test_get_total_pages_espaco_em_volta_do_link_de_ultima_casa():
    # O rótulo é comparado sem espaço nem quebra de linha em volta; um
    # template reindentado não pode transformar o » em paginador sem ».
    html = _primeira_pagina_com(
        '<a class="page-link" href="/jurisprudences/search?page=5515&amp;q=dano+moral">\n  &raquo; \n</a>'
    )
    assert _get_total_pages(html) == 5515


def test_get_total_pages_link_de_ultima_com_page_zero_levanta():
    # page=0 passa no teste de dígito; sem a checagem N >= 1 o total seria 0
    # e o download pararia na primeira página sem erro.
    html = _primeira_pagina_com(
        '<a class="page-link" href="/jurisprudences/search?page=0&amp;q=dano+moral">&raquo;</a>'
    )
    with pytest.raises(ValueError, match="TJPI: link de última página"):
        _get_total_pages(html)


def test_get_total_pages_link_de_ultima_com_digito_unicode_levanta():
    # "²" passa em ``str.isdigit`` mas ``int()`` o recusa com uma mensagem
    # genérica; o erro precisa ser o do TJPI, que diz o que estava no href.
    html = _primeira_pagina_com(
        '<a class="page-link" href="/jurisprudences/search?page=²&amp;q=dano+moral">&raquo;</a>'
    )
    with pytest.raises(ValueError, match="TJPI: link de última página"):
        _get_total_pages(html)


def test_get_total_pages_dois_links_de_ultima_discordantes_no_mesmo_paginador_levantam():
    # O primeiro » de cada paginador traz 5515, então os dois paginadores
    # concordam se só o primeiro contar; o segundo », com 7, tem que pesar.
    link_7 = '<a class="page-link" href="/jurisprudences/search?page=7&amp;q=dano+moral">&raquo;</a>'
    html = _primeira_pagina_com(_LINK_ULTIMA + link_7)
    with pytest.raises(ValueError, match="discordam"):
        _get_total_pages(html)


def test_get_total_pages_dois_links_de_ultima_iguais_no_mesmo_paginador():
    html = _primeira_pagina_com(_LINK_ULTIMA + _LINK_ULTIMA)
    assert _get_total_pages(html) == 5515
