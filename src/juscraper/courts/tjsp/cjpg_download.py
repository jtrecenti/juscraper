"""Downloads cases from the TJSP jurisprudence search."""
import logging
import os
import time
from datetime import datetime
from typing import Optional

import requests
from tqdm import tqdm

from ...utils.cnj import clean_cnj

# Limite imposto pelo backend do eSAJ no campo "pesquisaLivre" do CJPG.
# Strings maiores são truncadas silenciosamente pelo TJSP.
_TJSP_PESQUISA_MAX_CHARS = 120


class QueryTooLongError(ValueError):
    """Raised when the search query exceeds the TJSP backend maximum length."""


def cjpg_download(
    pesquisa: str,
    session: requests.Session,
    u_base: str,
    download_path: str,
    sleep_time: float = 0.5,
    classes: Optional['list[str] | None'] = None,
    assuntos: Optional['list[str] | None'] = None,
    varas: Optional['list[str] | None'] = None,
    id_processo: Optional['str | None'] = None,
    data_inicio: Optional['str | None'] = None,
    data_fim: Optional['str | None'] = None,
    paginas: Optional['list | range | None'] = None,
    get_n_pags_callback=None
):
    """Download cases from the TJSP jurisprudence search.

    Args:
        pesquisa (str): The search query for the jurisprudence. Maximum 120 characters
            (TJSP backend limit).
        session (requests.Session): Authenticated session.
        u_base (str): Base URL of the ESAJ.
        download_path (str): Base directory for saving files.
        sleep_time (float): Time to wait between requests.
        classes (list[str], optional): Filters for classes.
        assuntos (list[str], optional): Filters for subjects.
        varas (list[str], optional): Filters for courts.
        id_processo (str, optional): Process ID.
        data_inicio (str, optional): Start date for filtering.
        data_fim (str, optional): End date for filtering.
        paginas (range, optional): Page range (1-based, e.g., range(1, 4) downloads pages 1-3).
        get_n_pags_callback (callable): Callback function to extract number of pages.
    """
    if pesquisa is not None and len(pesquisa) > _TJSP_PESQUISA_MAX_CHARS:
        raise QueryTooLongError(
            f"O campo 'pesquisa' do CJPG do TJSP aceita no máximo "
            f"{_TJSP_PESQUISA_MAX_CHARS} caracteres "
            f"(recebido: {len(pesquisa)} caracteres). "
            "Reduza a busca ou divida em consultas menores."
        )
    assuntos_str = ','.join(assuntos) if assuntos is not None else None
    varas_str = ','.join(varas) if varas is not None else None
    classes_str = ','.join(classes) if classes is not None else None
    id_processo_str = clean_cnj(id_processo) if id_processo is not None else ''

    query = {
        'conversationId': '',
        'dadosConsulta.pesquisaLivre': pesquisa,
        'tipoNumero': 'UNIFICADO',
        'numeroDigitoAnoUnificado': id_processo_str[:15],
        'foroNumeroUnificado': id_processo_str[-4:],
        'dadosConsulta.nuProcesso': id_processo_str,
        'classeTreeSelection.values': classes_str,
        'assuntoTreeSelection.values': assuntos_str,
        'dadosConsulta.dtInicio': data_inicio,
        'dadosConsulta.dtFim': data_fim,
        'varasTreeSelection.values': varas_str,
        'dadosConsulta.ordenacao': 'DESC'
    }

    # Busca a primeira página
    r0 = session.get(f"{u_base}cjpg/pesquisar.do", params=query)
    try:
        if get_n_pags_callback is None:
            raise ValueError(
                "É necessário fornecer get_n_pags_callback para extrair o número de páginas."
            )
        n_pags = get_n_pags_callback(r0)
    except Exception as e:
        # Salvar HTML bruto para debug
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        debug_dir = os.path.join(download_path, "cjpg_debug")
        if not os.path.isdir(debug_dir):
            os.makedirs(debug_dir)
        debug_file = os.path.join(debug_dir, f"cjpg_primeira_pagina_{timestamp}.html")
        with open(debug_file, 'w', encoding='utf-8') as f:
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
    if not os.path.isdir(path):
        os.makedirs(path)

    # Zero-results short-circuit: save the form page so ``cjpg_parse_manager``
    # has at least one file to process (returns an empty DataFrame). Refs #109.
    if n_pags == 0:
        with open(f"{path}/cjpg_00001.html", 'w', encoding='utf-8') as f:
            f.write(r0.text)
        return path

    # Se paginas for None, definir range para todas as páginas (1-based)
    if paginas is None:
        paginas = range(1, n_pags + 1)
    elif isinstance(paginas, range):
        start = paginas.start if paginas.start is not None else 1
        stop = min(paginas.stop, n_pags + 1) if paginas.stop is not None else n_pags + 1
        step = paginas.step if paginas.step is not None else 1
        paginas = range(start, stop, step)
    else:
        # list — cap to available pages
        paginas = [p for p in paginas if p <= n_pags]

    # Save page 1 from the initial request (r0) if it's in the requested range
    first_page_in_range = 1 in paginas
    if first_page_in_range:
        with open(f"{path}/cjpg_00001.html", 'w', encoding='utf-8') as f:
            f.write(r0.text)

    # Download remaining pages (> 1) via trocarDePagina.do
    remaining = [p for p in paginas if p > 1]
    total = len(remaining) + (1 if first_page_in_range else 0)
    initial = 1 if first_page_in_range else 0

    for page in tqdm(remaining, desc="Baixando documentos", total=total, initial=initial):
        time.sleep(sleep_time)
        u = f"{u_base}cjpg/trocarDePagina.do?pagina={page}&conversationId="
        r = session.get(u)
        with open(f"{path}/cjpg_{page:05d}.html", 'w', encoding='utf-8') as f:  # noqa: E231
            f.write(r.text)
    return path
