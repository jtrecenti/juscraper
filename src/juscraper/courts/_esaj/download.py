"""Shared POST-then-paginated-GET download flow for eSAJ cjsg.

Absorbs the near-identical ``cjsg_download.py`` modules from the five eSAJ
puros (TJAC/TJAL/TJAM/TJCE/TJMS) plus TJSP's ``cjsg_download.py``. TJSP
sends a slightly different form body (handled via ``body_builder``), a
Chrome-flavoured User-Agent (``chrome_ua``), and extracts a
``conversationId`` from the first page that is propagated to subsequent
pages.

Todas as chamadas HTTP — POST inicial (``resultadoCompleta.do``), GET da
primeira página (``trocaDePagina.do?pagina=1``, usado também para
descobrir o total de páginas) e GETs paginados — delegam ao retry
centralizado :meth:`juscraper.core.http.HTTPScraper._request_with_retry`
(backoff exponencial, ``Retry-After`` numérico, retry em 403/429/5xx).
Originalmente (#203) apenas os GETs paginados estavam cobertos; o gap do
POST/GET inicial foi fechado no #255 (refs #233).

``_request_with_retry`` é API contratual de ``HTTPScraper`` para subclasses
e código irmão em ``juscraper.courts.*``: o underscore marca "interno ao
juscraper" (não exportado em ``__all__``), não "privado da instância".
Decisão registrada em #201. Daí o ``pylint: disable=protected-access``
abaixo no nível de módulo.
"""
# pylint: disable=protected-access
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from tqdm import tqdm

if TYPE_CHECKING:
    from ...core.http import HTTPScraper

logger = logging.getLogger("juscraper._esaj.download")

_ESAJ_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
}

_CHROME_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    ),
}


def _extract_conversation_id(html: str) -> str:
    """Extract ``<input name="conversationId" value="...">`` if present."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        elem = soup.find("input", {"name": "conversationId"})
        if elem is not None:
            return str(elem.get("value", "") or "")
    except (ValueError, AttributeError):
        pass
    return ""


def fetch_cjsg_first_page(
    *,
    scraper: "HTTPScraper",
    base_url: str,
    body: dict,
    tipo_decisao: str,
    sleep_time: float = 1.0,
    chrome_ua: bool = False,
) -> str:
    """Run ``POST resultadoCompleta + GET pagina=1`` and return the HTML.

    Shared by :func:`download_cjsg_pages` (continues into paginated download)
    and by the ``count_only=True`` short-circuit in
    :meth:`EsajSearchScraper.cjsg` (issue #92), which only needs the
    first-page HTML to extract ``n_results``.

    Side effect: updates ``scraper.session.headers`` with the eSAJ or Chrome
    UA, mirroring :func:`download_cjsg_pages`.

    Args:
        scraper: :class:`HTTPScraper` providing ``session`` and
            ``_request_with_retry`` (#203 retry policy).
        base_url: ``https://esaj.<tribunal>.jus.br/`` (trailing slash).
        body: Form body for ``POST cjsg/resultadoCompleta.do``.
        tipo_decisao: ``"acordao"`` or ``"monocratica"``.
        sleep_time: Seconds between the POST and the subsequent GET.
        chrome_ua: When ``True`` sends the Chrome UA (TJSP); otherwise the
            polite juscraper UA.

    Returns:
        First-page HTML as a ``str`` (latin1-decoded).
    """
    session = scraper.session
    session.headers.update(_CHROME_HEADERS if chrome_ua else _ESAJ_HEADERS)

    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    link_cjsg = f"{base_url}cjsg/resultadoCompleta.do"
    first_page_url = f"{base_url}cjsg/trocaDePagina.do?tipoDeDecisao={tipo_param}&pagina=1"

    # Body do POST descartado: a resposta é só o "ack" do form submit; o HTML
    # com os resultados vem do GET subsequente em ``trocaDePagina.do?pagina=1``.
    scraper._request_with_retry(
        "POST", link_cjsg, data=body, timeout=30, allow_redirects=True,
    )

    time.sleep(sleep_time)
    first_resp = scraper._request_with_retry(
        "GET",
        first_page_url,
        timeout=30,
        headers={"Accept": "text/html; charset=latin1;", "Referer": link_cjsg},
    )
    first_resp.encoding = "latin1"
    return first_resp.text


def _pages_to_fetch(
    paginas: "list | range | None" | None,
    n_pags: int,
) -> list[int]:
    """Return the list of pages >1 that should still be fetched after page 1."""
    if paginas is None:
        return list(range(2, n_pags + 1))
    if isinstance(paginas, range):
        pag_max = min(paginas.stop, n_pags + 1) if paginas.stop is not None else n_pags + 1
        start = paginas.start if paginas.start is not None else 1
        return [p for p in range(start, pag_max) if p > 1]
    # list
    return [p for p in paginas if 1 < p <= n_pags]


def _page1_in_range(paginas: "list | range | None" | None) -> bool:
    if paginas is None:
        return True
    if isinstance(paginas, range):
        start = paginas.start if paginas.start is not None else 1
        return start <= 1
    return 1 in paginas


def download_cjsg_pages(
    *,
    scraper: "HTTPScraper",
    base_url: str,
    download_path: str,
    body: dict,
    tipo_decisao: str,
    paginas: "list | range | None" | None,
    get_n_pags_callback: Callable[[str], int],
    sleep_time: float = 1.0,
    chrome_ua: bool = False,
    extract_conversation_id: bool = False,
    progress_desc: str = "Baixando documentos",
) -> str:
    """Execute the eSAJ cjsg two-step flow and save raw HTML files.

    Args:
        scraper: :class:`HTTPScraper` que provê ``session`` (com adapters já
            montados — TJCE TLS via ``_configure_session``) e o método
            ``_request_with_retry`` usado nos GETs paginados (#203).
        base_url: ``https://esaj.<tribunal>.jus.br/`` (trailing slash).
        download_path: Base directory; actual files land under
            ``<download_path>/cjsg/<YYYYMMDDHHMMSS>/cjsg_NNNNN.html``.
        body: Form body for ``POST cjsg/resultadoCompleta.do``. Must include
            ``tipoDecisaoSelecionados`` (``A`` or ``D``).
        tipo_decisao: ``"acordao"`` or ``"monocratica"``. Echoed in the
            ``trocaDePagina.do`` query string as ``tipoDeDecisao``.
        paginas: 1-based page selector. ``None`` means all available pages.
        get_n_pags_callback: Callable that receives the first-page HTML and
            returns the total page count.
        sleep_time: Seconds between requests.
        chrome_ua: When ``True`` sends the Chrome UA (TJSP). Otherwise sends
            the polite juscraper UA (other 5 eSAJ puros).
        extract_conversation_id: When ``True`` parses ``conversationId`` from
            page 1 and appends it to subsequent GETs (TJSP).
        progress_desc: Label passed to tqdm.

    Returns:
        Path to the directory containing the downloaded files.
    """
    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = Path(download_path) / "cjsg" / timestamp
    path.mkdir(parents=True, exist_ok=True)

    link_cjsg = f"{base_url}cjsg/resultadoCompleta.do"

    logger.info("Submetendo formulário de busca...")
    first_html = fetch_cjsg_first_page(
        scraper=scraper,
        base_url=base_url,
        body=body,
        tipo_decisao=tipo_decisao,
        sleep_time=sleep_time,
        chrome_ua=chrome_ua,
    )

    n_pags = get_n_pags_callback(first_html)

    with (path / "cjsg_00001.html").open("w", encoding="latin1") as fp:
        fp.write(first_html)

    if n_pags == 0:
        logger.info("Nenhum resultado encontrado para a busca.")
        return str(path)

    conversation_id = _extract_conversation_id(first_html) if extract_conversation_id else ""

    paginas_list = _pages_to_fetch(paginas, n_pags)
    if not paginas_list:
        logger.info("Total de páginas: %s. Baixando apenas a primeira.", n_pags)
        return str(path)

    logger.info("Total de páginas: %s. Baixando: %s", n_pags, len(paginas_list) + 1)

    total_pages = len(paginas_list) + (1 if _page1_in_range(paginas) else 0)
    initial = 1 if _page1_in_range(paginas) else 0

    for pag in tqdm(paginas_list, desc=progress_desc, total=total_pages, initial=initial):
        time.sleep(sleep_time)
        query: dict[str, object] = {"tipoDeDecisao": tipo_param, "pagina": pag}
        if conversation_id:
            query["conversationId"] = conversation_id

        resp = scraper._request_with_retry(
            "GET",
            f"{base_url}cjsg/trocaDePagina.do",
            params=query,
            timeout=30,
            headers={"Accept": "text/html; charset=latin1;", "Referer": link_cjsg},
        )
        resp.encoding = "latin1"
        with (path / f"cjsg_{pag:05d}.html").open("w", encoding="latin1") as fp:
            fp.write(resp.text)

    return str(path)


__all__ = ["download_cjsg_pages", "fetch_cjsg_first_page"]
