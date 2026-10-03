"""Downloads raw results from the TJPI jurisprudence search (HTML scraping)."""
import re
import time
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from tqdm import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import extract_count_with_cascade, parse_page_number, resolve_total_pages

BASE_URL = "https://jurisprudencia.tjpi.jus.br/jurisprudences/search"
RESULTS_PER_PAGE = 25


def build_cjsg_params(
    pesquisa: str,
    page: int = 1,
    tipo: str = "",
    relator: str = "",
    classe: str = "",
    orgao: str = "",
    data_min: str = "",
    data_max: str = "",
) -> dict:
    """Build the query-string params dict for the TJPI CJSG search endpoint.

    ``data_min``/``data_max`` are the BFF date filter (ISO ``YYYY-MM-DD``);
    they are wired by ``TJPIScraper.cjsg`` after going through
    ``normalize_datas`` + ``to_iso_date``.
    """
    params = {"q": pesquisa, "page": str(page)}
    if tipo:
        params["tipo"] = tipo
    if relator:
        params["relator"] = relator
    if classe:
        params["classe"] = classe
    if orgao:
        params["orgao"] = orgao
    if data_min:
        params["data_min"] = data_min
    if data_max:
        params["data_max"] = data_max
    return params


_LAST_PAGE_TEXT = "\u00bb"  # », rótulo do link de última página
# Cascata da contagem. O rótulo fica num ``div.pb-3`` (o primeiro desses é o
# formulário de filtros, que nenhuma regex casa); se a classe mudar, a cascata
# cai no HTML bruto, e por isso as duas regex exigem "jurisprudência(s)" logo
# após o número: "de um total de 84 prestações" numa ementa não casa.
_COUNT_SELECTORS = ("div.pb-3",)
# O número vem em ``<b>``; ``_SEP`` aceita espaço e tag entre as palavras para
# que a mesma regex sirva ao texto do ``div.pb-3`` e ao HTML bruto do fallback.
_SEP = r"(?:\s|&nbsp;|<[^>]+>)*"
_COUNT_PATTERNS = (
    # Várias páginas: "Exibindo 1 - 25 de um total de <b>137865</b> jurisprudência(s)".
    re.compile(rf"de um total de{_SEP}([\d.]+){_SEP}jurisprud", re.IGNORECASE),
    # Página única: "Exibindo <b>5</b> jurisprudência(s)".
    re.compile(rf"Exibindo{_SEP}([\d.]+){_SEP}jurisprud", re.IGNORECASE),
)
_ZERO_MARKERS = ("Sem resultados para",)


def _last_page_links(soup: BeautifulSoup) -> set[int]:
    """Lê os totais dos links ``»`` da página inteira.

    O link de última página não tem classe, ``rel`` nem ``aria-label``
    próprios: é um ``a.page-link`` como os numerados, e só o rótulo ``»``
    o distingue. A busca cobre a página inteira, e não só ``ul.pagination``,
    para que uma troca de tema do paginador não esconda o link da conferência.
    """
    totais = set()
    for link in soup.select("a[href]"):
        if link.get_text(strip=True) != _LAST_PAGE_TEXT:
            continue
        pagina = parse_qs(urlparse(str(link["href"])).query).get("page", [""])[0]
        totais.add(parse_page_number(pagina, tribunal="TJPI", origem=f"link » {link['href']!r}"))
    return totais


def _get_total_pages(html: str) -> int:
    """Extrai o total de páginas da primeira página de resultados.

    O total sai da contagem "de um total de N jurisprudência(s)" dividida por
    ``RESULTS_PER_PAGE``, e os links ``»`` da página são conferidos contra ele
    por :func:`~juscraper.utils.pagination.resolve_total_pages`. Vale para a
    primeira página, a única que ``cjsg_download_manager`` lê.

    Raises:
        ValueError: Nos casos de :func:`~juscraper.utils.pagination.resolve_total_pages`
            e de :func:`~juscraper.utils.pagination.parse_page_number`.
    """
    n_resultados = extract_count_with_cascade(
        html,
        css_selectors=_COUNT_SELECTORS,
        regex_patterns=_COUNT_PATTERNS,
        zero_markers=_ZERO_MARKERS,
    )
    return resolve_total_pages(
        n_resultados,
        resultados_por_pagina=RESULTS_PER_PAGE,
        totais_links=_last_page_links(BeautifulSoup(html, "html.parser")),
        tribunal="TJPI",
    )


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    sleep_time: float = 1.0,
    **kwargs,
) -> list:
    """Download raw HTML pages from the TJPI jurisprudence search.

    Returns a list of raw HTML strings (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJPIScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx.
        sleep_time: Delay (em segundos) entre páginas. Default 1.0; o client
            normalmente passa ``self.sleep_time`` herdado de ``HTTPScraper``.
        **kwargs: Additional filter parameters (tipo, relator, classe, orgao).

    Raises:
        ValueError: Com ``paginas=None``, quando a primeira página não permite
            fixar o total de páginas; os casos estão em :func:`_get_total_pages`.
            O download para depois da primeira requisição, em vez de estimar.
    """
    def _get_page(pagina_1based: int) -> str:
        params = build_cjsg_params(pesquisa=pesquisa, page=pagina_1based, **kwargs)
        resp = request_fn("GET", BASE_URL, params=params, timeout=30)
        resp.encoding = "utf-8"
        return resp.text

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        n_pags = _get_total_pages(first)
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJPI"):
                time.sleep(sleep_time)
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJPI"):
        if resultados:
            time.sleep(sleep_time)
        resultados.append(_get_page(pagina_1based))
    return resultados
