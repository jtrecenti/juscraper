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
from .exceptions import QueryTooLongError

__all__ = ["QueryTooLongError", "cjpg_download", "fetch_cjpg_first_page"]


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
    paginas: 'list | range | None' = None,
    get_n_pags_callback=None,
):
    """Download cases from the TJSP jurisprudence search.

    Internal helper — the public scraper entry point
    (:meth:`TJSPScraper.cjpg_download`) runs ``validate_pesquisa_length``
    and pydantic validation before calling this function. Direct callers
    must validate ``pesquisa`` upstream.

    ``classe``/``assunto``/``vara`` chegam ja como CSV (ou ``None``); a coercao
    de ``int``/``list`` -> CSV acontece no schema (:class:`InputCJPGTJSP`) via
    :data:`IdFiltro`. Refs #232.

    Raises:
        ValueError: If ``get_n_pags_callback`` is missing or fails to
            extract the page count from the first-page HTML.
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
    try:
        if get_n_pags_callback is None:
            raise ValueError(
                "É necessário fornecer get_n_pags_callback para extrair o número de páginas."
            )
        n_pags = get_n_pags_callback(r0)
    except Exception as e:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        debug_dir = Path(download_path) / "cjpg_debug"
        if not debug_dir.is_dir():
            debug_dir.mkdir(parents=True)
        debug_file = debug_dir / f"cjpg_primeira_pagina_{timestamp}.html"
        with debug_file.open('w', encoding='utf-8') as f:
            f.write(r0.text)
        logger = logging.getLogger("juscraper.cjpg_download")
        logger.error(
            "Erro ao extrair número de páginas: %s. HTML salvo em: %s",
            str(e),
            debug_file
        )
        raise ValueError(
            f"Erro ao extrair número de páginas: {e}. HTML salvo em: {debug_file}"
        ) from e

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{download_path}/cjpg/{timestamp}"
    if not Path(path).is_dir():
        Path(path).mkdir(parents=True)

    if n_pags == 0:
        with Path(f"{path}/cjpg_00001.html").open('w', encoding='utf-8') as f:
            f.write(r0.text)
        return path

    if paginas is None:
        paginas = range(1, n_pags + 1)
    elif isinstance(paginas, range):
        start = paginas.start if paginas.start is not None else 1
        stop = min(paginas.stop, n_pags + 1) if paginas.stop is not None else n_pags + 1
        step = paginas.step if paginas.step is not None else 1
        paginas = range(start, stop, step)
    else:
        paginas = [p for p in paginas if p <= n_pags]

    first_page_in_range = 1 in paginas
    if first_page_in_range:
        with Path(f"{path}/cjpg_00001.html").open('w', encoding='utf-8') as f:
            f.write(r0.text)

    remaining = [p for p in paginas if p > 1]
    total = len(remaining) + (1 if first_page_in_range else 0)
    initial = 1 if first_page_in_range else 0

    for page in tqdm(remaining, desc="Baixando documentos", total=total, initial=initial):
        time.sleep(sleep_time)
        u = f"{u_base}cjpg/trocarDePagina.do?pagina={page}&conversationId="
        r = session.get(u)
        with Path(f"{path}/cjpg_{page:05d}.html").open('w', encoding='utf-8') as f:  # noqa: E231
            f.write(r.text)
    return path
