"""Downloads cases from the TJSP jurisprudence search (CJPG).

CJPG internals are TJSP-specific and not refactored by #84 (no duplication
across tribunals to absorb). ``QueryTooLongError`` is re-exported from the
canonical location :mod:`juscraper.courts.tjsp.exceptions` so legacy tests
can continue importing it from here.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import requests
from tqdm import tqdm

from ...utils.cnj import clean_cnj
from .cjpg_parse import cjpg_n_pags
from .exceptions import QueryTooLongError

__all__ = ["QueryTooLongError", "cjpg_download", "fetch_cjpg_first_page"]


def _save_debug_html(response: requests.Response, download_path: str, error: Exception) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    debug_dir = Path(download_path) / "cjpg_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / f"cjpg_primeira_pagina_{timestamp}.html"
    debug_file.write_text(response.text, encoding="utf-8")
    logging.getLogger("juscraper.cjpg_download").error(
        "Erro ao extrair número de páginas: %s. HTML salvo em: %s",
        str(error),
        debug_file,
    )
    return debug_file


def _extract_page_count(
    response: requests.Response,
    download_path: str,
) -> int:
    try:
        return cjpg_n_pags(response.content)
    except Exception as error:
        debug_file = _save_debug_html(response, download_path, error)
        raise ValueError(
            f"Erro ao extrair número de páginas: {error}. HTML salvo em: {debug_file}"
        ) from error


def _normalize_pages(paginas: list[int] | range | None, n_pags: int) -> list[int] | range:
    if paginas is None:
        return range(1, n_pags + 1)
    if isinstance(paginas, range):
        return range(paginas.start, min(paginas.stop, n_pags + 1), paginas.step)
    return [page for page in paginas if page <= n_pags]


def _save_page(path: Path, page: int, html: str) -> None:
    path.joinpath(f"cjpg_{page:05d}.html").write_text(html, encoding="utf-8")


def fetch_cjpg_first_page(
    *,
    pesquisa: str,
    session: requests.Session,
    u_base: str,
    classe: str | None = None,
    assunto: str | None = None,
    vara: str | None = None,
    id_processo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> requests.Response:
    """Run the CJPG initial GET and return the raw :class:`requests.Response`.

    Shared by :func:`cjpg_download` (continues into paginated download) and
    by the ``count_only=True`` short-circuit in :meth:`TJSPScraper.cjpg`
    (issue #92), which only needs the first-page HTML.

    Returns the response (not just ``.text``) so that the download path can
    persist it to disk and the count-only path can extract ``n_results``
    from ``.text`` without an extra request.
    """
    id_processo_str = clean_cnj(id_processo) if id_processo is not None else ''

    query = {
        'conversationId': '',
        'dadosConsulta.pesquisaLivre': pesquisa,
        'tipoNumero': 'UNIFICADO',
        'numeroDigitoAnoUnificado': id_processo_str[:15],
        'foroNumeroUnificado': id_processo_str[-4:],
        'dadosConsulta.nuProcesso': id_processo_str,
        'classeTreeSelection.values': classe,
        'assuntoTreeSelection.values': assunto,
        'dadosConsulta.dtInicio': data_inicio,
        'dadosConsulta.dtFim': data_fim,
        'varasTreeSelection.values': vara,
        'dadosConsulta.ordenacao': 'DESC'
    }

    return session.get(f"{u_base}cjpg/pesquisar.do", params=query)


def cjpg_download(
    pesquisa: str,
    session: requests.Session,
    u_base: str,
    download_path: str,
    sleep_time: float = 0.5,
    classe: str | None = None,
    assunto: str | None = None,
    vara: str | None = None,
    id_processo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    paginas: list[int] | range | None = None,
) -> str:
    """Download cases from the TJSP jurisprudence search.

    Internal helper — the public scraper entry point
    (:meth:`TJSPScraper.cjpg_download`) runs ``validate_pesquisa_length``
    and pydantic validation before calling this function. Direct callers
    must validate ``pesquisa`` upstream.

    ``classe``/``assunto``/``vara`` chegam ja como CSV (ou ``None``); a coercao
    de ``int``/``list`` -> CSV acontece no schema (:class:`InputCJPGTJSP`) via
    :data:`IdFiltro`. Refs #232.

    Raises:
        ValueError: If the page count cannot be extracted from the first-page
            HTML. The response is saved for diagnosis before raising.
    """
    r0 = fetch_cjpg_first_page(
        pesquisa=pesquisa,
        session=session,
        u_base=u_base,
        classe=classe,
        assunto=assunto,
        vara=vara,
        id_processo=id_processo,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    n_pags = _extract_page_count(r0, download_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(download_path) / "cjpg" / timestamp
    path.mkdir(parents=True, exist_ok=True)

    if n_pags == 0:
        _save_page(path, 1, r0.text)
        return str(path)

    paginas = _normalize_pages(paginas, n_pags)

    first_page_in_range = 1 in paginas
    if first_page_in_range:
        _save_page(path, 1, r0.text)

    remaining = [p for p in paginas if p > 1]
    total = len(remaining) + (1 if first_page_in_range else 0)
    initial = 1 if first_page_in_range else 0

    for page in tqdm(remaining, desc="Baixando documentos", total=total, initial=initial):
        time.sleep(sleep_time)
        u = f"{u_base}cjpg/trocarDePagina.do?pagina={page}&conversationId="
        r = session.get(u)
        _save_page(path, page, r.text)
    return str(path)
