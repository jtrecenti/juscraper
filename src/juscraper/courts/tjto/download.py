"""
Downloads raw pages from the TJTO jurisprudence search.
"""
import math
import re
import time
from collections.abc import Callable
from typing import Any

from tqdm import tqdm

from juscraper.core.exceptions import BotChallengeBlockedError, ColetaParcialError
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import descrever_paginas, extract_count_with_cascade, menor_pagina, paginas_no_intervalo
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


def _get_total_results(html: str) -> int:
    """Extract the total number of results from the active tab's count.

    Sem ``zero_markers``: a página além do total também diz "Nenhum documento
    encontrado", mas a aba traz o total da busca (``pagina_alem_do_total.html``);
    a busca sem resultados traz ``(0)`` na aba.
    """
    n = extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
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
    resp = request_fn("GET", EMENTA_URL, params={"id": uuid}, perfil="ementa")
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
        paginas: Pages to download (1-based). None = all. A menor página pedida
            sai antes, e o total dela descarta, sem requisição e com aviso no
            logger ``juscraper.tjto``, as páginas além do fim da busca.
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

    def _get_page(pagina: int) -> str:
        payload = build_cjsg_payload(termo, start=(pagina - 1) * RESULTS_PER_PAGE, **fetch_kwargs)
        resp = request_fn("POST", BASE_URL, data=payload, perfil="cjsg")
        return resp.text

    # A menor página pedida é a única baixada antes de saber o total: se ela
    # passa do total, as demais também passam, e todas caem no aviso.
    primeira = menor_pagina(paginas)
    html_primeira = _get_page(primeira)
    total = _get_total_results(html_primeira)
    n_pags = math.ceil(total / RESULTS_PER_PAGE) if total else 1
    validas = paginas_no_intervalo(paginas, n_pags, tribunal="TJTO")
    return _baixar_paginas(_get_page, validas, primeira, html_primeira, sleep_time)


def _baixar_paginas(
    get_page: Callable[[int], str], paginas: list[int], primeira: int, html_primeira: str, sleep_time: float
) -> list:
    """Baixa as ``paginas`` (1-based), com ``sleep_time`` antes de cada requisição.

    ``primeira`` já foi baixada, para ler o total, e entra na sua posição sem
    nova requisição. Por isso a página que falha aqui sempre tem outra baixada
    e levanta :class:`ColetaParcialError`, com as baixadas lidas em
    ``.resultado`` (``primeira`` também, se viria depois na ordem pedida), como
    no TJMG: o bloqueio do AWS WAF, que chega depois de algumas buscas
    seguidas, não descarta o que já veio. A falha na própria ``primeira`` sobe
    antes, como a exceção original.
    """
    resultados: list[str] = []
    for posicao, page_num in enumerate(tqdm(paginas, desc="Baixando páginas TJTO")):
        if page_num == primeira:
            resultados.append(html_primeira)
            continue
        time.sleep(sleep_time)
        try:
            resultados.append(get_page(page_num))
        except Exception as exc:  # vai para ColetaParcialError
            faltando = paginas[posicao:]
            if primeira in faltando:
                resultados.append(html_primeira)
                faltando.remove(primeira)
            raise _coleta_parcial(resultados, faltando, exc) from exc
    return resultados


def _coleta_parcial(resultados: list[str], faltando: list[int], exc: Exception) -> ColetaParcialError:
    """``ColetaParcialError`` com as páginas baixadas antes de ``faltando[0]`` falhar."""
    mensagem = (
        f"TJTO: a página {faltando[0]} falhou ({exc!r}), e a busca parou. "
        f"As {len(resultados)} página(s) baixadas antes estão, já lidas, no atributo .resultado do erro; "
        f"faltam as páginas {descrever_paginas(faltando)}, que podem ser pedidas de novo com paginas="
    )
    if isinstance(exc, BotChallengeBlockedError):
        mensagem += " depois de pelo menos 10 minutos, quando o bloqueio do AWS WAF passa"
    return ColetaParcialError(mensagem + ".", resultado=cjsg_parse_manager(resultados), falhas=[(None, None, exc)])
