"""
Downloads cases from the TJSP jurisprudence search.
"""
import logging
import os
import time
from datetime import datetime

import requests
from tqdm import tqdm

from ...utils.cnj import clean_cnj


def cjpg_download(
    pesquisa: str,
    session: requests.Session,
    u_base: str,
    download_path: str,
    sleep_time: float = 0.5,
    classes: list[str] = None,
    assuntos: list[str] = None,
    varas: list[str] = None,
    id_processo: str = None,
    data_inicio: str = None,
    data_fim: str = None,
    paginas: range = None,
    get_n_pags_callback=None
):
    """
    Downloads cases from the TJSP jurisprudence search.

    Args:
        pesquisa (str): The search query for the jurisprudence.
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
        paginas (range, optional): Page range.
        get_n_pags_callback (callable): Callback function to extract number of pages.
    """
    if assuntos is not None:
        assuntos = ','.join(assuntos)
    if varas is not None:
        varas = ','.join(varas)
    if classes is not None:
        classes = ','.join(classes)
    if id_processo is not None:
        id_processo = clean_cnj(id_processo)
    else:
        id_processo = ''

    query = {
        'conversationId': '',
        'dadosConsulta.pesquisaLivre': pesquisa,
        'tipoNumero': 'UNIFICADO',
        'numeroDigitoAnoUnificado': id_processo[:15],
        'foroNumeroUnificado': id_processo[-4:],
        'dadosConsulta.nuProcesso': id_processo,
        'classeTreeSelection.values': classes,
        'assuntoTreeSelection.values': assuntos,
        'dadosConsulta.dtInicio': data_inicio,
        'dadosConsulta.dtFim': data_fim,
        'varasTreeSelection.values': varas,
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
        
        # Log de debug: número de páginas identificado
        logger = logging.getLogger("juscraper.cjpg_download")
        logger.debug("DEBUG: Número de páginas identificado pelo callback: %d", n_pags)
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

    # Se paginas for None, definir range para todas as páginas
    if paginas is None:
        paginas = range(1, n_pags + 1)
        logger.debug("DEBUG: Range de páginas definido automaticamente: %d até %d (total: %d páginas)", 
                    1, n_pags, n_pags)
    else:
        start, stop, step = paginas.start, min(paginas.stop, n_pags + 1), paginas.step
        paginas = range(start, stop, step)
        logger.debug("DEBUG: Range de páginas fornecido pelo usuário: %d até %d (step: %d, total: %d páginas)", 
                    start, stop-1, step, len(paginas))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{download_path}/cjpg/{timestamp}"
    if not os.path.isdir(path):
        os.makedirs(path)

    logger.debug("DEBUG: Iniciando download das páginas. Diretório: %s", path)
    
    pages_downloaded = 0
    for pag in tqdm(paginas, desc="Baixando documentos"):
        time.sleep(sleep_time)
        u = f"{u_base}cjpg/trocarDePagina.do?pagina={pag + 1}&conversationId="
        
        # Log detalhado a cada 100 páginas ou para as primeiras 5 páginas
        if pag <= 5 or pag % 100 == 0:
            logger.debug("DEBUG: Baixando página %d de %d. URL: %s", pag, len(paginas), u)
        
        r = session.get(u)
        file_name = f"{path}/cjpg_{pag + 1:05d}.html"
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(r.text)
        pages_downloaded += 1
    
    # Log final: contagem de arquivos salvos
    files_saved = len([f for f in os.listdir(path) if f.endswith('.html')])
    logger.debug("DEBUG: Download concluído. Páginas processadas: %d, Arquivos salvos: %d", 
                pages_downloaded, files_saved)
    
    return path
