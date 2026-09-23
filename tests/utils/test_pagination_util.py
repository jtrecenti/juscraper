"""Testes do util ``extract_count_with_cascade`` (refs #87)."""
from __future__ import annotations

import re

from juscraper.utils.pagination import extract_count_with_cascade


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


def test_selector_miss_falls_back_to_raw_html():
    html = "<html><body><span>120 documentos encontrados</span></body></html>"
    assert extract_count_with_cascade(
        html,
        css_selectors=("td.totalResultados",),
        regex_patterns=(re.compile(r"(\d+)\s+documentos\s+encontrados",),),
    ) == 120


def test_fallback_max_int_picks_largest():
    html = "<html><body>pagina 1 de 12, mostrando 10 itens</body></html>"
    assert extract_count_with_cascade(
        html,
        regex_patterns=(),
        fallback_max_int=True,
    ) == 12


def test_no_match_without_fallback_returns_none():
    html = "<html><body>nada aqui</body></html>"
    assert extract_count_with_cascade(
        html,
        regex_patterns=(re.compile(r"(\d+)\s+resultados"),),
        fallback_max_int=False,
    ) is None


def test_default_fallback_is_off():
    """Default ``fallback_max_int=False`` evita extrair numero qualquer da pagina."""
    html = "<html><body>pagina 1 de 12, mostrando 10 itens</body></html>"
    assert extract_count_with_cascade(html, regex_patterns=()) is None


def test_zero_marker_short_circuits():
    html = """
    <html><body>
      <p>Nenhum resultado foi encontrado</p>
      <span>pagina 1 de 5</span>
    </body></html>
    """
    assert extract_count_with_cascade(
        html,
        css_selectors=("span",),
        regex_patterns=(re.compile(r"de\s+(\d+)"),),
        zero_markers=("nenhum resultado",),
    ) == 0


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


def test_zero_marker_case_insensitive():
    html = "<body><p>NENHUM RESULTADO</p><span>10 paginas</span></body>"
    assert extract_count_with_cascade(
        html,
        regex_patterns=(re.compile(r"(\d+)\s+pagina"),),
        zero_markers=("nenhum resultado",),
    ) == 0


def test_use_element_html_keeps_attributes():
    html = '<a class="page-link" href="/x?page=99">»</a>'
    assert extract_count_with_cascade(
        html,
        css_selectors=("a.page-link",),
        regex_patterns=(re.compile(r"page=(\d+)"),),
        use_element_html=True,
    ) == 99


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
    ) == 77


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


def test_fallback_max_int_only_reads_first_candidate():
    html = "<span class='first'>page 1 of 12</span><span class='second'>page 99</span>"

    assert extract_count_with_cascade(
        html,
        css_selectors=("span.first", "span.second"),
        regex_patterns=(),
        fallback_max_int=True,
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
