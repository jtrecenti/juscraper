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
    digits = raw.replace(".", "")
    return int(digits) if digits.isdigit() else None


def _extract_from_match(match: re.Match[str]) -> int | None:
    for group in match.groups():
        if group is None:
            continue
        coerced = _coerce_int(group)
        if coerced is not None:
            return coerced
    return _coerce_int(match.group(0))


def extract_count_with_cascade(
    html: str,
    *,
    css_selectors: Sequence[str] = (),
    regex_patterns: Sequence[re.Pattern[str]] = (),
    zero_markers: Sequence[str] = (),
    fallback_max_int: bool = True,
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
        regex_patterns: Regex tentadas em ordem para cada texto candidato.
            Se a regex tem grupos, retorna o primeiro grupo numerico
            valido; caso contrario tenta ``group(0)``.
        zero_markers: Substrings (case-insensitive) que, quando presentes
            no texto da pagina, indicam zero resultados — caminho rapido,
            evita extrair ``0`` por engano de markup com numero da
            paginacao "Resultados 1 ate 0 de 0".
        fallback_max_int: Se ``True`` (default), ultimo recurso e pegar
            ``max(\\d+)`` no primeiro candidato. Util para layouts onde
            varios numeros aparecem mas o total e o maior. Se ``False``,
            falha ao retornar ``None`` — caller controla.
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

    if zero_markers:
        text_lower = soup.get_text(" ", strip=True).lower()
        for marker in zero_markers:
            if marker.lower() in text_lower:
                return 0

    candidates: list[str] = []
    for selector in css_selectors:
        for el in soup.select(selector):
            content = str(el) if use_element_html else el.get_text(" ", strip=True)
            if content:
                candidates.append(content)

    if not candidates:
        candidates = [html]

    if aggregate == "max":
        all_matches: list[int] = []
        for txt in candidates:
            for pattern in regex_patterns:
                for raw in pattern.findall(txt):
                    coerced = _coerce_int(raw if isinstance(raw, str) else raw[0])
                    if coerced is not None:
                        all_matches.append(coerced)
        if all_matches:
            return max(all_matches)
    else:
        for txt in candidates:
            for pattern in regex_patterns:
                match = pattern.search(txt)
                if match:
                    value = _extract_from_match(match)
                    if value is not None:
                        return value

    if fallback_max_int and candidates:
        valid_nums: list[int] = []
        for raw in _FALLBACK_NUMERO_RE.findall(candidates[0]):
            coerced = _coerce_int(raw)
            if coerced is not None:
                valid_nums.append(coerced)
        if valid_nums:
            return max(valid_nums)

    return None
