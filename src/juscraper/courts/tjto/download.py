"""
Downloads raw pages from the TJTO jurisprudence search.
"""
import math
import re
import time
from collections.abc import Callable
from typing import Any

from tqdm import tqdm

from juscraper.core.exceptions import ColetaParcialError
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import extract_count_with_cascade
from juscraper.utils.params import to_br_date

from .parse import cjsg_parse_manager

BASE_URL = "https://jurisprudencia.tjto.jus.br/consulta.php"
EMENTA_URL = "https://jurisprudencia.tjto.jus.br/ementa.php"
RESULTS_PER_PAGE = 20

# type_minuta_selected: 1 = Acórdãos, 2 = Decisões Monocráticas, 3 = Sentenças
TYPE_MINUTA_MAP = {
    "acordaos": "1",
    "decisoes": "2",
    "sentencas": "3",
}


_PAGINATION_CSS_SELECTORS: tuple[str, ...] = (
    ".nav-link.active .num_minuta",
    ".nav-link.active span",
)
_PAGINATION_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\((\d[\d.]*)\s*resultados?\)", re.IGNORECASE),
    re.compile(r"\(([\d.]+)\)"),
)
_ZERO_MARKERS: tuple[str, ...] = ("nenhum documento encontrado",)


def _get_total_results(html: str) -> int:
    """Extract the total number of results from the active tab's count."""
    n = extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
        zero_markers=_ZERO_MARKERS,
        fallback_max_int=False,
    )
    return n if n is not None else 0


def build_cjsg_payload(
    termo: str,
    start: int = 0,
    *,
    type_minuta: str = "1",
    tip_criterio_inst: str = "",
    tip_criterio_data: str = "DESC",
    numero_processo: str = "",
    dat_jul_ini: str = "",
    dat_jul_fim: str = "",
    soementa: bool = False,
) -> dict:
    """Build the form-encoded body for the TJTO jurisprudence search.

    Shared by ``cjsg`` and ``cjpg``: only ``tip_criterio_inst`` differs
    (``'2'`` for the 2nd-instance shortcut, ``'1'`` for the 1st-instance
    shortcut). ``start`` is a 0-based Solr offset
    (page = ``start // RESULTS_PER_PAGE + 1``). The backend only applies
    ``dat_jul_ini``/``dat_jul_fim`` when ``tempo_julgados="pers"`` (the
    "Intervalo personalizado" option in the UI); an empty value silently
    falls back to "all dates".
    """
    dat_ini_br = to_br_date(dat_jul_ini) or ""
    dat_fim_br = to_br_date(dat_jul_fim) or ""
    tempo_julgados = "pers" if (dat_ini_br or dat_fim_br) else ""
    payload: dict[str, str] = {
        "start": str(start),
        "rows": str(RESULTS_PER_PAGE),
        "type_minuta_selected": type_minuta,
        "q": termo,
        "tip_criterio_inst": tip_criterio_inst,
        "tip_criterio_data": tip_criterio_data,
        "numero_processo": numero_processo,
        "tempo_julgados": tempo_julgados,
        "dat_jul_ini": dat_ini_br,
        "dat_jul_fim": dat_fim_br,
    }
    if soementa:
        payload["soementa"] = "on"
    return payload


def _fetch_ementa(request_fn: RequestFn, uuid: str) -> dict[Any, Any]:
    """Fetch ementa JSON for a given document UUID."""
    resp = request_fn("GET", EMENTA_URL, params={"id": uuid}, timeout=30)
    data = resp.json()
    docs = data.get("response", {}).get("docs", [])
    doc: dict[Any, Any] = docs[0] if docs else {}
    return doc


def cjsg_download_manager(
    termo: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    sleep_time: float = 1.0,
    type_minuta: str = "1",
    tip_criterio_inst: str = "",
    tip_criterio_data: str = "DESC",
    numero_processo: str = "",
    dat_jul_ini: str = "",
    dat_jul_fim: str = "",
    soementa: bool = False,
) -> list:
    """Download raw HTML pages from TJTO jurisprudence search.

    Args:
        termo: Search term.
        paginas: Pages to download (1-based). None = all.
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJTOScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx.
        sleep_time: Delay (em segundos) entre páginas. Default 1.0; o client
            normalmente passa ``self.sleep_time`` herdado de ``HTTPScraper``.
        type_minuta: '1' (Acórdãos), '2' (Decisões Monocráticas), '3' (Sentenças).

    Returns:
        List of raw HTML strings, one per page.
    """
    fetch_kwargs: dict[str, Any] = {
        "type_minuta": type_minuta,
        "tip_criterio_inst": tip_criterio_inst,
        "tip_criterio_data": tip_criterio_data,
        "numero_processo": numero_processo,
        "dat_jul_ini": dat_jul_ini,
        "dat_jul_fim": dat_jul_fim,
        "soementa": soementa,
    }

    def _get_page(start: int) -> str:
        payload = build_cjsg_payload(termo, start=start, **fetch_kwargs)
        resp = request_fn("POST", BASE_URL, data=payload, timeout=60)
        return resp.text

    if paginas is None:
        first_html = _get_page(0)
        total = _get_total_results(first_html)
        n_pages = math.ceil(total / RESULTS_PER_PAGE) if total else 1
        return _baixar_paginas(_get_page, list(range(2, n_pages + 1)), [first_html], sleep_time)
    return _baixar_paginas(_get_page, list(paginas), [], sleep_time)


def _baixar_paginas(
    get_page: Callable[[int], str], paginas: list[int], resultados: list[str], sleep_time: float
) -> list:
    """Acrescenta a ``resultados`` as ``paginas`` (1-based), com ``sleep_time`` entre elas.

    A página que falha com outra já baixada levanta :class:`ColetaParcialError`,
    com as anteriores lidas em ``.resultado``, como no TJMG: o bloqueio do AWS
    WAF, que chega depois de algumas buscas seguidas, não descarta o que já
    veio. Sem página baixada antes, a exceção original sobe.
    """
    for posicao, page_num in enumerate(tqdm(paginas, desc="Baixando páginas TJTO")):
        if resultados:
            time.sleep(sleep_time)
        try:
            resultados.append(get_page((page_num - 1) * RESULTS_PER_PAGE))
        except Exception as exc:  # noqa: BLE001 - vai para ColetaParcialError
            if not resultados:
                raise
            raise _coleta_parcial(resultados, paginas[posicao:], exc) from exc
    return resultados


def _coleta_parcial(resultados: list[str], faltando: list[int], exc: Exception) -> ColetaParcialError:
    """``ColetaParcialError`` com as páginas baixadas antes de ``faltando[0]`` falhar."""
    return ColetaParcialError(
        f"TJTO: a página {faltando[0]} falhou ({exc!r}), e a busca parou. "
        f"As {len(resultados)} página(s) baixadas antes estão, já lidas, no atributo .resultado do erro; "
        f"faltam as páginas {faltando}, que podem ser pedidas de novo com paginas=. "
        "Se foi o bloqueio do AWS WAF, aguarde pelo menos 10 minutos.",
        resultado=cjsg_parse_manager(resultados),
        falhas=[(None, None, exc)],
    )
