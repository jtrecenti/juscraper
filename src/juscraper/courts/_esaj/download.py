"""Shared POST-then-paginated-GET download flow for eSAJ cjsg.

Absorbs the near-identical ``cjsg_download.py`` modules from the five eSAJ
puros (TJAC/TJAL/TJAM/TJCE/TJMS) plus TJSP's ``cjsg_download.py``. TJSP
sends a slightly different form body (handled via ``body_builder``), a
Chrome-flavoured User-Agent (``chrome_ua``), and extracts a
``conversationId`` from the first page that is propagated to subsequent
pages.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

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


def _pages_to_fetch(
    paginas: Optional["list | range | None"],
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


def _page1_in_range(paginas: Optional["list | range | None"]) -> bool:
    if paginas is None:
        return True
    if isinstance(paginas, range):
        start = paginas.start if paginas.start is not None else 1
        return start <= 1
    return 1 in paginas


def download_cjsg_pages(
    *,
    session: requests.Session,
    base_url: str,
    download_path: str,
    body: dict,
    tipo_decisao: str,
    paginas: Optional["list | range | None"],
    get_n_pags_callback: Callable[[str], int],
    sleep_time: float = 1.0,
    chrome_ua: bool = False,
    extract_conversation_id: bool = False,
    progress_desc: str = "Baixando documentos",
) -> str:
    """Execute the eSAJ cjsg two-step flow and save raw HTML files.

    Args:
        session: HTTP session. Caller attaches custom adapters (e.g. TJCE TLS).
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
    session.headers.update(_CHROME_HEADERS if chrome_ua else _ESAJ_HEADERS)

    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = os.path.join(download_path, "cjsg", timestamp)
    os.makedirs(path, exist_ok=True)

    link_cjsg = f"{base_url}cjsg/resultadoCompleta.do"
    first_page_url = f"{base_url}cjsg/trocaDePagina.do?tipoDeDecisao={tipo_param}&pagina=1"

    logger.info("Submetendo formulário de busca...")
    post_resp = session.post(link_cjsg, data=body, timeout=30, allow_redirects=True)
    post_resp.raise_for_status()

    time.sleep(sleep_time)
    first_resp = session.get(
        first_page_url,
        timeout=30,
        headers={"Accept": "text/html; charset=latin1;", "Referer": link_cjsg},
    )
    first_resp.raise_for_status()
    first_resp.encoding = "latin1"
    first_html = first_resp.text

    n_pags = get_n_pags_callback(first_html)

    with open(os.path.join(path, "cjsg_00001.html"), "w", encoding="latin1") as fp:
        fp.write(first_html)

    if n_pags == 0:
        logger.info("Nenhum resultado encontrado para a busca.")
        return path

    conversation_id = _extract_conversation_id(first_html) if extract_conversation_id else ""

    paginas_list = _pages_to_fetch(paginas, n_pags)
    if not paginas_list:
        logger.info("Total de páginas: %s. Baixando apenas a primeira.", n_pags)
        return path

    logger.info("Total de páginas: %s. Baixando: %s", n_pags, len(paginas_list) + 1)

    total_pages = len(paginas_list) + (1 if _page1_in_range(paginas) else 0)
    initial = 1 if _page1_in_range(paginas) else 0

    for pag in tqdm(paginas_list, desc=progress_desc, total=total_pages, initial=initial):
        time.sleep(sleep_time)
        query: dict[str, object] = {"tipoDeDecisao": tipo_param, "pagina": pag}
        if conversation_id:
            query["conversationId"] = conversation_id

        _fetch_page_with_retry(
            session=session,
            url=f"{base_url}cjsg/trocaDePagina.do",
            params=query,
            referer=f"{base_url}cjsg/resultadoCompleta.do",
            destination=os.path.join(path, f"cjsg_{pag:05d}.html"),
            sleep_time=sleep_time,
        )

    return path


def _fetch_page_with_retry(
    *,
    session: requests.Session,
    url: str,
    params: dict,
    referer: str,
    destination: str,
    sleep_time: float,
    max_attempts: int = 3,
) -> None:
    """Fetch one paginated GET with exponential backoff, save latin-1 bytes."""
    for attempt in range(max_attempts):
        try:
            resp = session.get(
                url,
                params=params,
                timeout=30,
                headers={"Accept": "text/html; charset=latin1;", "Referer": referer},
            )
            resp.encoding = "latin1"
            resp.raise_for_status()
            with open(destination, "w", encoding="latin1") as fp:
                fp.write(resp.text)
            return
        except requests.RequestException as exc:
            if attempt == max_attempts - 1:
                logger.error(
                    "Erro ao baixar %s após %s tentativas: %s",
                    params.get("pagina"), max_attempts, exc,
                )
                raise
            logger.warning(
                "Tentativa %s/%s falhou para pagina=%s: %s",
                attempt + 1, max_attempts, params.get("pagina"), exc,
            )
            time.sleep(sleep_time * (attempt + 1))


__all__ = ["download_cjsg_pages"]
