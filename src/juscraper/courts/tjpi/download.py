"""Downloads raw results from the TJPI jurisprudence search (HTML scraping)."""
import time
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag
from tqdm import tqdm

from juscraper.core.http import RequestFn

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


_PAGINATOR_SELECTOR = "ul.pagination"
_LAST_PAGE_TEXT = "\u00bb"  # », rotulo do link de ultima pagina


def _last_page_from_paginator(paginator: Tag) -> int:
    """Le o ``page=N`` do link ``»`` de um paginador.

    O link de ultima pagina nao tem classe, ``rel`` nem ``aria-label``
    proprios: e um ``a.page-link`` como os numerados, e so o rotulo ``»``
    o distingue. A posicao (ultimo ``li``) nao serve, porque sem o ``»`` o
    ultimo item passa a ser o ``›``, que aponta para a pagina seguinte.
    """
    for link in paginator.select("a[href]"):
        if link.get_text(strip=True) != _LAST_PAGE_TEXT:
            continue
        page = parse_qs(urlparse(str(link["href"])).query).get("page", [""])[0]
        if not page.isdigit():
            raise ValueError(f"TJPI: link de última página sem page=N no href: {link['href']!r}")
        return int(page)
    raise ValueError(
        "TJPI: paginador sem o link de última página (»); "
        "o total de páginas não pode ser determinado sem estimar."
    )


def _get_total_pages(html: str) -> int:
    """Extrai o total de paginas da primeira pagina de resultados.

    O total vem do link ``»`` do paginador, e nao do maior ``page=N``: o
    paginador mostra so uma janela de paginas, e sem o ``»`` o maior numero
    visivel e o fim da janela, nao o total. Sem ``ul.pagination`` a busca
    tem uma pagina so (ou nenhum resultado) e o retorno e 1.

    Vale para a primeira pagina, a unica que ``cjsg_download_manager`` le.
    O paginador esconde os links que nao levam a lugar nenhum: a pagina 1
    nao traz ``«`` nem ``‹``, que aparecem na 2, e pelo mesmo padrao a
    ultima pagina deve omitir ``»``. Na pagina 1, porem, busca de pagina
    unica nao tem paginador, entao paginador sem ``»`` so ocorre se o
    markup mudou. O TJPI desenha dois paginadores iguais, acima e abaixo
    da lista; todos precisam trazer o ``»`` com o mesmo total.

    Raises:
        ValueError: Paginador sem o link ``»``, ``»`` sem ``page=N`` ou
            paginadores com totais diferentes.
    """
    paginators = BeautifulSoup(html, "html.parser").select(_PAGINATOR_SELECTOR)
    if not paginators:
        return 1
    totals = {_last_page_from_paginator(paginator) for paginator in paginators}
    if len(totals) > 1:
        raise ValueError(f"TJPI: paginadores discordam do total de páginas: {sorted(totals)}")
    return totals.pop()


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
