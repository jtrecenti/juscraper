"""Testes dos utils de paginação.

``extract_count_with_cascade`` (refs #87), ``resolve_total_pages`` e ``parse_page_number``.
"""
from __future__ import annotations

import re

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from juscraper.core.exceptions import ColetaParcialError
from juscraper.schemas import PaginasMixin
from juscraper.utils.pagination import (
    AvisoVazio,
    baixar_paginas_pedidas,
    descrever_paginas,
    extract_count_with_cascade,
    maior_pagina,
    menor_pagina,
    pagina_pedida,
    paginas_no_intervalo,
    paginas_unicas,
    parse_page_number,
    recusar_alem_do_teto,
    resolve_total_pages,
    selecao_de_paginas,
)

P = selecao_de_paginas


def test_selector_and_regex_match():
    html = """
    <html><body>
      <td class="totalResultados"><b>45</b> resultados encontrados</td>
    </body></html>
    """
    assert extract_count_with_cascade(
        html,
        css_selectors=("td.totalResultados",),
        regex_patterns=(re.compile(r"(\d+)\s*resultados?", re.IGNORECASE),),
    ) == 45


def test_selector_miss_nao_le_o_html_bruto():
    """Com seletores, as regex não rodam no HTML inteiro, onde estão as ementas."""
    html = "<html><body><p>Contrato de compra e venda (fevereiro de 2009).</p></body></html>"
    assert extract_count_with_cascade(
        html,
        css_selectors=("span.ui-paginator-current",),
        regex_patterns=(re.compile(r"de\s+(\d+)\)"),),
    ) is None


def test_selector_miss_falls_back_to_raw_html_com_fallback_html():
    html = "<html><body><span>120 documentos encontrados</span></body></html>"
    assert extract_count_with_cascade(
        html,
        css_selectors=("td.totalResultados",),
        regex_patterns=(re.compile(r"(\d+)\s+documentos\s+encontrados",),),
        fallback_html=True,
    ) == 120


def test_sem_seletores_html_bruto_so_com_fallback_html():
    html = "<html><body><span>120 documentos encontrados</span></body></html>"
    regex = (re.compile(r"(\d+)\s+documentos\s+encontrados"),)
    assert extract_count_with_cascade(html, regex_patterns=regex) is None
    assert extract_count_with_cascade(html, regex_patterns=regex, fallback_html=True) == 120


def test_tag_restringe_a_cascata_ao_trecho():
    """Com uma ``Tag``, seletores, regex e marcadores de zero só veem o trecho."""
    soup = BeautifulSoup(
        "<div id='a'><span class='n'>45 resultados</span></div>"
        "<div id='b'>Nenhum documento encontrado; 99 resultados</div>",
        "html.parser",
    )
    regex = (re.compile(r"(\d+)\s*resultados?"),)
    trecho = soup.find(id="a")

    assert extract_count_with_cascade(trecho, css_selectors=("span.n",), regex_patterns=regex) == 45
    assert extract_count_with_cascade(
        trecho, css_selectors=("td.ausente",), regex_patterns=regex, fallback_html=True
    ) == 45
    aviso = AvisoVazio(("div",), ("nenhum documento",))
    ausente = ("td.ausente",)
    assert extract_count_with_cascade(trecho, css_selectors=ausente, regex_patterns=regex, aviso_vazio=aviso) is None
    assert extract_count_with_cascade(soup, css_selectors=("span.n",), regex_patterns=regex, aviso_vazio=aviso) == 45
    assert extract_count_with_cascade(soup, css_selectors=ausente, regex_patterns=regex, aviso_vazio=aviso) == 0


def test_contagem_achada_vence_o_marcador_de_zero():
    """Uma ementa que cita o marcador não zera a contagem que a cascata achou."""
    html = """
    <html><body>
      <span class="total">pagina 1 de 5</span>
      <p>Ementa: nenhum resultado foi encontrado nas buscas de bens.</p>
    </body></html>
    """
    assert extract_count_with_cascade(
        html,
        css_selectors=("span.total",),
        regex_patterns=(re.compile(r"de\s+(\d+)"),),
        aviso_vazio=AvisoVazio(("p",), ("nenhum resultado",)),
    ) == 5


def test_aviso_vazio_vale_quando_a_cascata_nao_acha_contagem():
    html = """
    <html><body>
      <div class="aviso">Nenhum resultado foi encontrado</div>
      <span class="total"></span>
    </body></html>
    """
    assert extract_count_with_cascade(
        html,
        css_selectors=("span.total",),
        regex_patterns=(re.compile(r"de\s+(\d+)"),),
        aviso_vazio=AvisoVazio(("div.aviso",), ("nenhum resultado",)),
    ) == 0


def test_aviso_vazio_fora_dos_seletores_nao_zera():
    """Sem contagem, a ementa que cita o marcador fora do contêiner do aviso não vira 0."""
    html = """
    <html><body>
      <div class="aviso"></div>
      <p class="ementa">Nenhum resultado foi encontrado nas buscas de bens.</p>
    </body></html>
    """
    assert extract_count_with_cascade(
        html,
        css_selectors=("span.total",),
        regex_patterns=(re.compile(r"de\s+(\d+)"),),
        aviso_vazio=AvisoVazio(("div.aviso", "td.aviso"), ("nenhum resultado",)),
    ) is None


def test_number_with_dots_is_normalized():
    html = "<td class='total'>1.234 resultados</td>"
    assert extract_count_with_cascade(
        html,
        css_selectors=("td.total",),
        regex_patterns=(re.compile(r"(\d[\d.]*)\s+resultados"),),
    ) == 1234


def test_first_selector_miss_second_match():
    html = """
    <html><body>
      <span class="total"></span>
      <div id="contagem">95 resultados</div>
    </body></html>
    """
    assert extract_count_with_cascade(
        html,
        css_selectors=("span.total", "#contagem"),
        regex_patterns=(re.compile(r"(\d+)\s+resultados"),),
    ) == 95


def test_first_regex_miss_second_match():
    html = "<td class='paginacao'>de 7 paginas</td>"
    assert extract_count_with_cascade(
        html,
        css_selectors=("td.paginacao",),
        regex_patterns=(
            re.compile(r"(\d+)\s+resultados"),
            re.compile(r"de\s+(\d+)\s+pagina"),
        ),
    ) == 7


def test_regex_without_groups_uses_group_zero():
    html = "<td class='total'>contagem 42</td>"
    assert extract_count_with_cascade(
        html,
        css_selectors=("td.total",),
        regex_patterns=(re.compile(r"\d+"),),
    ) == 42


def test_aviso_vazio_sem_diferenca_de_maiusculas_e_em_qualquer_seletor():
    html = "<body><div class='a'>outro aviso</div><p>NENHUM RESULTADO</p><span>sem paginas</span></body>"
    assert extract_count_with_cascade(
        html,
        regex_patterns=(re.compile(r"(\d+)\s+pagina"),),
        aviso_vazio=AvisoVazio(("div.a", "p"), ("nao achado", "Nenhum Resultado")),
    ) == 0


def test_first_uses_first_numeric_group_across_optional_groups():
    html = "<div class='counter'>pages: 27</div>"

    assert extract_count_with_cascade(
        html,
        css_selectors=("div.counter",),
        regex_patterns=(re.compile(r"(?:results:\s*(\d+)|pages:\s*(\d+))"),),
    ) == 27


def test_first_ignores_later_numeric_groups_in_same_match():
    html = "<div class='counter'>page 4 of 90</div>"

    assert extract_count_with_cascade(
        html,
        css_selectors=("div.counter",),
        regex_patterns=(re.compile(r"page\s+(\d+)\s+of\s+(\d+)"),),
    ) == 4


def test_empty_selector_candidates_fall_back_to_raw_html():
    html = "<span class='empty'> </span><meta data-total='77'>"

    assert extract_count_with_cascade(
        html,
        css_selectors=("span.empty",),
        regex_patterns=(re.compile(r"data-total=['\"](\d+)"),),
        fallback_html=True,
    ) == 77
    assert extract_count_with_cascade(
        html,
        css_selectors=("span.empty",),
        regex_patterns=(re.compile(r"data-total=['\"](\d+)"),),
    ) is None


def test_first_preserves_selector_and_element_order_while_skipping_empty():
    html = """
    <span class="primary"> </span>
    <span class="primary">12 resultados</span>
    <span class="primary">14 resultados</span>
    <span class="secondary">99 resultados</span>
    """

    assert extract_count_with_cascade(
        html,
        css_selectors=("span.primary", "span.secondary"),
        regex_patterns=(re.compile(r"(\d+)\s+resultados"),),
    ) == 12


def test_number_with_comma_is_normalized():
    html = "<span class='total'>1,234 resultados</span>"

    assert extract_count_with_cascade(
        html,
        css_selectors=("span.total",),
        regex_patterns=(re.compile(r"(\d[\d.,]*)\s+resultados"),),
    ) == 1234


def test_first_tries_every_regex_on_a_candidate_before_the_next_candidate():
    html = "<span class='a'>7 docs</span><span class='b'>total 9</span>"

    assert extract_count_with_cascade(
        html,
        css_selectors=("span.a", "span.b"),
        regex_patterns=(re.compile(r"total (\d+)"), re.compile(r"(\d+) docs")),
    ) == 7


def test_first_skips_match_without_number_and_tries_next_regex():
    # Um grupo como ``([\d.]+)`` pode capturar so ``"."``, que nao vira
    # numero; a cascata tem de seguir para a proxima regex em vez de
    # devolver ``None`` na primeira que casou.
    html = "<span class='t'>total: . / 5 resultados</span>"

    assert extract_count_with_cascade(
        html,
        css_selectors=("span.t",),
        regex_patterns=(
            re.compile(r"total:\s*([\d.]+)"),
            re.compile(r"(\d+)\s+resultados"),
        ),
    ) == 5


@pytest.mark.parametrize(
    ("n_resultados", "esperado"),
    [(0, 1), (1, 1), (50, 1), (51, 2), (4795, 96), (410614, 8213)],
)
def test_resolve_total_pages_arredonda_para_cima(n_resultados, esperado):
    assert resolve_total_pages(n_resultados, resultados_por_pagina=50, tribunal="TJXX") == esperado


def test_resolve_total_pages_link_que_bate_e_aceito():
    assert resolve_total_pages(4795, resultados_por_pagina=50, totais_links={96}, tribunal="TJXX") == 96


@pytest.mark.parametrize("totais_links", [{480}, {1}, {96, 97}])
def test_resolve_total_pages_link_divergente_levanta(totais_links):
    with pytest.raises(ValueError, match="TJXX: o link de última página aponta"):
        resolve_total_pages(4795, resultados_por_pagina=50, totais_links=totais_links, tribunal="TJXX")


def test_resolve_total_pages_sem_contagem_levanta_mesmo_com_link():
    with pytest.raises(ValueError, match="TJXX: a página lida não traz a contagem"):
        resolve_total_pages(None, resultados_por_pagina=50, totais_links={96}, tribunal="TJXX")


def test_parse_page_number_aceita_digitos_ascii():
    assert parse_page_number("5515", tribunal="TJXX", origem="link") == 5515


@pytest.mark.parametrize("valor", ["", "0", "00", "-1", "²", "５５１５", " 12", "12\n", "1.0"])
def test_parse_page_number_rejeita(valor):
    with pytest.raises(ValueError, match="TJXX: link sem número de página válido"):
        parse_page_number(valor, tribunal="TJXX", origem="link")


def test_paginas_no_intervalo_mantem_a_ordem_e_avisa_as_de_fora(caplog):
    with caplog.at_level("WARNING", logger="juscraper.tjxx"):
        assert paginas_no_intervalo(P([3, 0, 1, 5, 2]), 3, tribunal="TJXX") == [3, 1, 2]

    # O aviso sai no logger do tribunal, como antes do helper, numa linha só.
    assert [(r.name, r.getMessage()) for r in caplog.records] == [
        ("juscraper.tjxx", "TJXX: páginas 0, 5 fora do intervalo 1-3"),
    ]


def test_paginas_no_intervalo_tira_repetidas_preservando_a_ordem(caplog):
    with caplog.at_level("WARNING", logger="juscraper.tjxx"):
        assert paginas_no_intervalo(P([2, 1, 2, 9, 1, 9]), 3, tribunal="TJXX") == [2, 1]

    assert [r.getMessage() for r in caplog.records] == ["TJXX: página 9 fora do intervalo 1-3"]


def test_paginas_no_intervalo_resume_muitas_paginas_de_fora_num_aviso(caplog):
    # ``paginas=1000`` (``range(1, 1001)``) numa busca de 7 páginas.
    with caplog.at_level("WARNING", logger="juscraper.tjxx"):
        assert paginas_no_intervalo(P(range(1, 1001)), 7, tribunal="TJXX") == list(range(1, 8))

    assert [r.getMessage() for r in caplog.records] == [
        "TJXX: páginas 8, 9, 10, 11, 12 e mais 988 fora do intervalo 1-7",
    ]


def test_paginas_no_intervalo_resume_lista_com_muitas_de_fora(caplog):
    with caplog.at_level("WARNING", logger="juscraper.tjxx"):
        assert paginas_no_intervalo(P([9, 0, 2, 8, 7, 6, 5, 9, 4]), 3, tribunal="TJXX") == [2]

    assert [r.getMessage() for r in caplog.records] == [
        "TJXX: páginas 9, 0, 8, 7, 6 e mais 2 fora do intervalo 1-3",
    ]


def test_paginas_no_intervalo_corta_range_sem_percorrer(caplog):
    # Como no ``PaginasMixin``: um range enorme não é percorrido página a página.
    with caplog.at_level("WARNING", logger="juscraper.tjxx"):
        assert paginas_no_intervalo(P(range(-1, 10**12, 3)), 9, tribunal="TJXX") == [2, 5, 8]

    assert [r.getMessage() for r in caplog.records] == [
        f"TJXX: páginas -1, 11, 14, 17, 20 e mais {len(range(-1, 10**12, 3)) - 3 - 5} fora do intervalo 1-9",
    ]


def test_paginas_no_intervalo_aceita_range_e_devolve_lista_vazia_sem_validas():
    assert paginas_no_intervalo(P(range(1, 4)), 3, tribunal="TJXX") == [1, 2, 3]
    assert paginas_no_intervalo(P(range(4, 6)), 3, tribunal="TJXX") == []


def test_paginas_no_intervalo_busca_vazia_nao_avisa(caplog):
    with caplog.at_level("WARNING", logger="juscraper.tjxx"):
        assert paginas_no_intervalo(P([1, 3]), 0, tribunal="TJXX") == []
    assert not caplog.records


def test_paginas_no_intervalo_sem_paginas_pedidas_devolve_todas():
    assert paginas_no_intervalo(P(None), 3, tribunal="TJXX") == [1, 2, 3]


@pytest.mark.parametrize(
    ("paginas", "menor", "maior"),
    [([3, 1, 5, 1], 1, 5), (range(2, 10**12, 3), 2, 10**12 - 2), (range(9, 0, -4), 1, 9), ([7], 7, 7)],
)
def test_menor_e_maior_pagina_sem_percorrer_range(paginas, menor, maior):
    assert (menor_pagina(P(paginas)), maior_pagina(P(paginas))) == (menor, maior)


def test_paginas_unicas_tira_repetidas_na_ordem_pedida():
    assert paginas_unicas(P([3, 1, 3, 2, 1])) == [3, 1, 2]


def test_paginas_unicas_devolve_range_sem_percorrer():
    paginas = range(1, 10**12, 2)
    assert paginas_unicas(P(paginas)) is paginas


def _baixar_com(paginas, n_pags, **kwargs):
    """``baixar_paginas_pedidas`` sobre páginas que são o próprio número: ``(pedidas, retorno)``."""
    pedidas: list[int] = []

    def buscar(pagina: int) -> int:
        pedidas.append(pagina)
        return pagina

    return pedidas, baixar_paginas_pedidas(P(paginas), buscar, lambda _first: n_pags, tribunal="TJXX", **kwargs)


class TestBaixarPaginasPedidas:
    """``baixar_paginas_pedidas``: ordem das requisições e do retorno, e espera entre pedidos."""

    @staticmethod
    def _baixar(paginas, n_pags=5, **kwargs):
        return _baixar_com(paginas, n_pags, **kwargs)

    def test_todas_as_paginas_na_ordem(self):
        assert self._baixar(None, n_pags=3) == ([1, 2, 3], [1, 2, 3])

    def test_menor_primeiro_e_retorno_na_ordem_pedida(self):
        assert self._baixar([4, 2, 4, 9]) == ([2, 4], [4, 2])

    def test_espera_antes_de_cada_pedido_depois_do_primeiro(self, mocker):
        sleep = mocker.patch("time.sleep")
        self._baixar([3, 1, 2], sleep_time=0.5)
        assert sleep.call_args_list == [mocker.call(0.5), mocker.call(0.5)]

    def test_sem_sleep_time_nao_espera(self, mocker):
        sleep = mocker.patch("time.sleep")
        self._baixar(None)
        sleep.assert_not_called()


class TestTeto:
    """``teto``: página além dele é erro antes de pedir; com ``None``, aviso e corte."""

    @pytest.mark.parametrize("paginas", [[1, 4], range(1, 10**9), [4]])
    def test_recusa_pagina_alem_do_teto_sem_requisicao(self, paginas):
        pedidas: list[int] = []
        mensagem = r"TJXX: o portal só entrega as 3 primeiras páginas.*página (4|999999999)\."
        with pytest.raises(ValueError, match=mensagem):
            baixar_paginas_pedidas(P(paginas), pedidas.append, lambda _first: 5, tribunal="TJXX", teto=3)
        assert pedidas == []

    @pytest.mark.parametrize(
        ("paginas", "baixadas"), [([3, 1], [3, 1]), (range(1, 4), [1, 2, 3]), (range(3, 0, -1), [3, 2, 1])]
    )
    def test_limita_paginas_explicitas_sem_aviso(self, paginas, baixadas, recwarn):
        assert _baixar_com(paginas, 5, teto=3)[1] == baixadas
        assert len(recwarn) == 0

    def test_avisa_quando_baixa_todas(self, recwarn):
        assert _baixar_com(None, 2, teto=3)[1] == [1, 2]
        assert len(recwarn) == 0
        with pytest.warns(UserWarning, match=r"TJXX: a busca tem 5 páginas, e o portal só entrega as 3 primeiras"):
            assert _baixar_com(None, 5, teto=3)[1] == [1, 2, 3]

    def test_recusar_alem_do_teto_aceita_none(self):
        recusar_alem_do_teto(None, 3, tribunal="TJXX")


class TestPaginasOpaca:
    """``Paginas`` só se lê pelos helpers: o laço à mão falha ao rodar."""

    @pytest.mark.parametrize(
        "leitura",
        [list, max, min, len, sorted, set, iter, lambda p: p[0], lambda p: 1 in p, lambda p: p.start, lambda p: [*p]],
    )
    @pytest.mark.parametrize("paginas", [[3, 1], range(1, 4)])
    def test_leitura_a_mao_levanta(self, leitura, paginas):
        with pytest.raises((TypeError, AttributeError)):
            leitura(P(paginas))

    def test_inteiro_vira_range_e_none_continua_none(self):
        assert P(3) == P(range(1, 4))
        assert P(None) is None
        assert P(P([2])) == P([2])
        assert repr(P([3, 1])) == "Paginas([3, 1])"

    def test_paginas_normalizadas_do_schema_e_opaca(self):
        assert PaginasMixin(paginas=2).paginas_normalizadas == P(range(1, 3))
        assert PaginasMixin().paginas_normalizadas is None

    @pytest.mark.parametrize(("paginas", "pagina", "pedida"), [(None, 7, True), ([3, 5], 5, True), ([3, 5], 4, False),
                                                               (range(1, 10**12, 2), 10**11 + 1, True)])
    def test_pagina_pedida(self, paginas, pagina, pedida):
        assert pagina_pedida(P(paginas), pagina) is pedida


@pytest.mark.parametrize(
    ("paginas", "texto"),
    [
        ([3], "[3]"),
        ([3, 4], "[3, 4]"),
        ([3, 4, 5], "range(3, 6)"),
        (list(range(2, 8241)), "range(2, 8241)"),
        ([2, 3, 5, 6], "[2, 3, 5, 6]"),
        ([5, 4, 3], "[5, 4, 3]"),
        ([1, 2, 3, 10**10], "[1, 2, 3, 10000000000]"),
        ([], "[]"),
    ],
)
def test_descrever_paginas_resume_a_sequencia_sem_saltos(paginas, texto):
    assert descrever_paginas(paginas) == texto


@pytest.mark.parametrize("paginas", [[3], [3, 4], list(range(2, 40)), [2, 3, 5, 6]])
def test_descrever_paginas_vale_como_paginas(paginas):
    # O texto da mensagem é o que o usuário cola em ``paginas=``.
    assert list(eval(descrever_paginas(paginas))) == paginas
