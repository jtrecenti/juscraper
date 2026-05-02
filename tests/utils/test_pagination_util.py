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


def test_aggregate_max_across_matches():
    html = """
    <ul class="pagination">
      <li><a href="?page=2">2</a></li>
      <li><a href="?page=10">10</a></li>
      <li><a href="?page=42">&raquo;</a></li>
    </ul>
    """
    assert extract_count_with_cascade(
        html,
        css_selectors=("ul.pagination",),
        regex_patterns=(re.compile(r"[?&]page=(\d+)"),),
        use_element_html=True,
        aggregate="max",
        fallback_max_int=False,
    ) == 42


def test_aggregate_max_no_matches_returns_none_when_fallback_off():
    html = '<div class="vazio"></div>'
    assert extract_count_with_cascade(
        html,
        css_selectors=("div.vazio",),
        regex_patterns=(re.compile(r"[?&]page=(\d+)"),),
        use_element_html=True,
        aggregate="max",
        fallback_max_int=False,
    ) is None


def test_use_element_html_keeps_attributes():
    html = '<a class="page-link" href="/x?page=99">»</a>'
    assert extract_count_with_cascade(
        html,
        css_selectors=("a.page-link",),
        regex_patterns=(re.compile(r"page=(\d+)"),),
        use_element_html=True,
    ) == 99
