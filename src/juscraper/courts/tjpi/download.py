"""Downloads raw results from the TJPI jurisprudence search (HTML scraping)."""
import re
import time
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import (
    baixar_paginas_pedidas,
    extract_count_with_cascade,
    menor_pagina,
    parse_page_number,
    resolve_total_pages,
)

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
# Cascata da contagem. O rótulo fica num ``<div class="pb-3">`` sem outra
# classe; o seletor exige a classe exata porque ``div.pb-3`` casaria também o
# contêiner da página (``content pt-3 pb-3 d-flex``), que guarda as ementas.
# O HTML da página só entra quando o seletor não casa nenhum elemento com texto,
# e por isso as duas regex começam em "Exibindo" e exigem "jurisprudência(s)"
# depois do número: "de um total de 84 prestações" numa ementa não casa. Se o
# seletor casar um div cujo texto as regex não reconhecem, a contagem vem
# ``None`` e, sem o marcador de busca vazia, ``resolve_total_pages`` levanta.
_COUNT_SELECTORS = ('div[class="pb-3"]',)
# O número vem em ``<b>``; ``_SEP`` aceita espaço e tag entre as palavras para
# que a mesma regex sirva ao texto do rótulo e ao HTML do fallback.
_SEP = r"(?:\s|&nbsp;|<[^>]+>)*"
_COUNT_PATTERNS = (
    # Várias páginas: "Exibindo 1 - 25 de um total de <b>137865</b> jurisprudência(s)".
    re.compile(
        rf"Exibindo{_SEP}[\d.]+{_SEP}-{_SEP}[\d.]+{_SEP}de um total de{_SEP}([\d.]+){_SEP}jurisprud",
        re.IGNORECASE,
    ),
    # Página única: "Exibindo <b>5</b> jurisprudência(s)".
    re.compile(rf"Exibindo{_SEP}([\d.]+){_SEP}jurisprud", re.IGNORECASE),
)
# Busca sem resultados: um nó de texto que começa com o marcador, seguido do
# termo pesquisado em outro div. O marcador só é consultado quando a contagem
# não aparece, e tem que abrir o nó de texto: "sem resultados para a
# localização de bens" no meio de uma ementa não zera a contagem.
_ZERO_MARKER = "Sem resultados para:"


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


def _sem_resultados(soup: BeautifulSoup) -> bool:
    return any(texto.strip().startswith(_ZERO_MARKER) for texto in soup.find_all(string=True))


def _get_total_pages(html: str) -> int:
    """Extrai o total de páginas de uma página de resultados.

    O total sai da contagem "de um total de N jurisprudência(s)" dividida por
    ``RESULTS_PER_PAGE``, e os links ``»`` da página são conferidos contra ele
    por :func:`~juscraper.utils.pagination.resolve_total_pages`. Toda página de
    resultados traz a contagem; ``cjsg_download_manager`` a lê na menor página pedida.

    Raises:
        ValueError: Nos casos de :func:`~juscraper.utils.pagination.resolve_total_pages`
            e de :func:`~juscraper.utils.pagination.parse_page_number`.
    """
    soup = BeautifulSoup(html, "html.parser")
    n_resultados = extract_count_with_cascade(
        soup,
        css_selectors=_COUNT_SELECTORS,
        regex_patterns=_COUNT_PATTERNS,
    )
    if n_resultados is None and _sem_resultados(soup):
        n_resultados = 0
    return resolve_total_pages(
        n_resultados,
        resultados_por_pagina=RESULTS_PER_PAGE,
        totais_links=_last_page_links(soup),
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
        ValueError: Quando a menor página pedida (a 1, com ``paginas=None``)
            não permite fixar o total de páginas; os casos estão em
            :func:`_get_total_pages`. O download para depois da primeira
            requisição, em vez de estimar.

    Quando a menor página pedida passa do total, o portal responde "Sem
    resultados para:"; a página 1 é então pedida só para ler o total da busca,
    que vai para o aviso das páginas fora do intervalo.
    """
    def _get_page(pagina_1based: int) -> str:
        params = build_cjsg_params(pesquisa=pesquisa, page=pagina_1based, **kwargs)
        resp = request_fn("GET", BASE_URL, params=params, perfil="cjsg")
        resp.encoding = "utf-8"
        return resp.text

    primeira = menor_pagina(paginas)

    def _n_pags(html: str) -> int:
        # A página além do total responde "Sem resultados para:", como a busca
        # vazia, e não traz a contagem; o total da busca sai da página 1.
        if primeira > 1 and _sem_resultados(BeautifulSoup(html, "html.parser")):
            time.sleep(sleep_time)
            html = _get_page(1)
        return _get_total_pages(html)

    return baixar_paginas_pedidas(paginas, _get_page, _n_pags, tribunal="TJPI", sleep_time=sleep_time)
