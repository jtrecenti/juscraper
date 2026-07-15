"""Cascata de seletores CSS + cascata de regex para extracao robusta de
contagem (numero de resultados ou de paginas) em paginas de tribunais.

Motivacao (refs #87): paginas de tribunais mudam markup sem aviso. Usar
regex unica em HTML cru (padrao antigo de varios scrapers) torna o
parser silenciosamente fragil. A estrategia canonica do projeto, ja
documentada para a familia eSAJ em ``cjsg_n_pags``, e tentar varios
seletores CSS em ordem ate algum casar e, no texto extraido, tentar
varias regex em ordem ate alguma achar o numero. Este modulo expoe essa
estrategia como helper generico para os tribunais nao-eSAJ.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from bs4 import BeautifulSoup

_FALLBACK_NUMERO_RE = re.compile(r"\d[\d.]*")


def _coerce_int(raw: str) -> int | None:
    digits = raw.replace(".", "").replace(",", "")
    return int(digits) if digits.isdigit() else None


def _extract_from_match(match: re.Match[str]) -> int | None:
    for group in match.groups():
        if group is None:
            continue
        coerced = _coerce_int(group)
        if coerced is not None:
            return coerced
    return _coerce_int(match.group(0))


def _has_zero_marker(soup: BeautifulSoup, zero_markers: Sequence[str]) -> bool:
    if not zero_markers:
        return False
    text_lower = soup.get_text(" ", strip=True).lower()
    return any(marker.lower() in text_lower for marker in zero_markers)


def _collect_candidates(
    soup: BeautifulSoup,
    html: str,
    css_selectors: Sequence[str],
    *,
    use_element_html: bool,
) -> list[str]:
    candidates: list[str] = []
    for selector in css_selectors:
        for element in soup.select(selector):
            content = str(element) if use_element_html else element.get_text(" ", strip=True)
            if content:
                candidates.append(content)
    return candidates or [html]


def _extract_first(
    candidates: Sequence[str],
    regex_patterns: Sequence[re.Pattern[str]],
) -> int | None:
    for candidate in candidates:
        for pattern in regex_patterns:
            match = pattern.search(candidate)
            if not match:
                continue
            value = _extract_from_match(match)
            if value is not None:
                return value
    return None


def _extract_from_findall_match(raw: str | tuple[str, ...]) -> int | None:
    groups = raw if isinstance(raw, tuple) else (raw,)
    for group in groups:
        value = _coerce_int(group)
        if value is not None:
            return value
    return None


def _extract_max(
    candidates: Sequence[str],
    regex_patterns: Sequence[re.Pattern[str]],
) -> int | None:
    values: list[int] = []
    for candidate in candidates:
        for pattern in regex_patterns:
            for raw in pattern.findall(candidate):
                value = _extract_from_findall_match(raw)
                if value is not None:
                    values.append(value)
    return max(values) if values else None


def _extract_fallback_max(candidate: str) -> int | None:
    values = [
        value
        for raw in _FALLBACK_NUMERO_RE.findall(candidate)
        if (value := _coerce_int(raw)) is not None
    ]
    return max(values) if values else None


def extract_count_with_cascade(
    html: str,
    *,
    css_selectors: Sequence[str] = (),
    regex_patterns: Sequence[re.Pattern[str]] = (),
    zero_markers: Sequence[str] = (),
    fallback_max_int: bool = False,
    use_element_html: bool = False,
    aggregate: Literal["first", "max"] = "first",
) -> int | None:
    r"""Extrai uma contagem (resultados ou paginas) usando cascata.

    O caller decide o que fazer quando a cascata falha (retorno ``None``):
    alguns tribunais convencionam ``return 1`` (assume pagina unica), outros
    ``return 0`` (assume zero resultados). Manter essa decisao do lado do
    caller preserva o comportamento legado de cada scraper.

    Args:
        html: HTML bruto da primeira pagina de resultados.
        css_selectors: Seletores CSS tentados em ordem. Para cada um,
            ``soup.select(selector)`` produz elementos cujo conteudo
            (texto ou HTML, conforme ``use_element_html``) vira candidato.
            Use ``()`` quando nao houver seletor estruturado confiavel —
            a cascata cai direto em ``regex_patterns`` sobre o HTML bruto.
            Se ``css_selectors`` e nao vazio mas nenhum seletor casa em
            nenhum elemento, a cascata tambem cai no HTML bruto.
        regex_patterns: Regex tentadas em ordem para cada texto candidato.
            Se a regex tem grupos, retorna o primeiro grupo numerico
            valido; caso contrario tenta ``group(0)``. Com
            ``aggregate="max"`` a regra e a mesma — em cada match, o
            primeiro grupo numerico valido (varrendo a tupla quando ha
            varios grupos) entra no acumulador para depois ser comparado.
        zero_markers: Substrings (case-insensitive) que, quando presentes
            em **qualquer lugar** do texto da pagina, fazem o util retornar
            ``0`` imediatamente — sem rodar a cascata de seletores. Use
            marcadores especificos do tribunal ("Nenhum documento
            encontrado", "Sua pesquisa nao retornou resultados") para nao
            falso-positivar em textos de ajuda.
        fallback_max_int: Se ``True``, ultimo recurso e pegar ``max(\\d+)``
            no primeiro candidato — util para layouts onde varios numeros
            aparecem mas o total e o maior. Default ``False`` (fail-fast:
            retorna ``None``). Os 5 callers atuais usam ``False`` e
            controlam o default semantico (1 pagina ou 0 resultados) do
            lado deles; ``True`` deve ser opt-in explicito para evitar
            extrair numeros irrelevantes da pagina (ano, codigo, etc.).
        use_element_html: Quando ``True``, cada candidato e o HTML completo
            do elemento (``str(el)``) em vez de apenas o texto. Necessario
            quando o numero alvo esta em atributo (ex.: ``href="?page=N"``
            em paginadores estilo Bootstrap).
        aggregate: ``"first"`` (default) retorna o primeiro match valido na
            ordem de cascata. ``"max"`` percorre TODOS os matches em todos
            os candidatos via ``pattern.findall`` e retorna o maior — util
            para paginadores que listam varios numeros de pagina (1, 2, …,
            N) e o "total" e ``max(N)``.

    Returns:
        ``int`` extraido ou ``None`` se nada casar e ``fallback_max_int``
        nao salvar. ``0`` quando ``zero_markers`` casarem.
    """
    soup = BeautifulSoup(html, "html.parser")
    if _has_zero_marker(soup, zero_markers):
        return 0

    candidates = _collect_candidates(
        soup,
        html,
        css_selectors,
        use_element_html=use_element_html,
    )
    value = (
        _extract_max(candidates, regex_patterns)
        if aggregate == "max"
        else _extract_first(candidates, regex_patterns)
    )
    if value is not None:
        return value
    if fallback_max_int:
        return _extract_fallback_max(candidates[0])
    return None
