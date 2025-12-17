"""
Downloads cases from the TJSP jurisprudence search.
"""
import logging
import os
import time
from datetime import datetime

import requests
from tqdm import tqdm
from bs4 import BeautifulSoup

from ...utils.cnj import clean_cnj

logger = logging.getLogger('juscraper.tjsp.cjpg_download')

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
        assuntos = get_tree_values(assuntos, session, "assunto")
    if varas is not None:
        varas = ','.join(varas)
    if classes is not None:
        classes = get_tree_values(classes, session, "classe")
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
    else:
        start, stop, step = paginas.start, min(paginas.stop, n_pags + 1), paginas.step
        paginas = range(start, stop, step)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{download_path}/cjpg/{timestamp}"
    if not os.path.isdir(path):
        os.makedirs(path)

    for pag in tqdm(paginas, desc="Baixando documentos"):
        time.sleep(sleep_time)
        u = f"{u_base}cjpg/trocarDePagina.do?pagina={pag + 1}&conversationId="
        r = session.get(u)
        file_name = f"{path}/cjpg_{pag + 1:05d}.html"
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(r.text)
    return path


def get_tree_values(items: list[str], session: requests.Session, tree_type: str = "classe") -> str | None:
    """
    Generic function to extract values from TJSP tree selectors.
    
    Args:
        items: List of text items to search for
        session: Requests session object
        tree_type: Type of tree - "classe" or "assunto"
    
    Returns:
        str: URL-encoded comma-separated values, or None if not all found
    """
    # Determine URL and field names based on tree type
    if tree_type == "classe":
        url = 'https://esaj.tjsp.jus.br/cjpg/classeTreeSelect.do?campoId=classe&mostrarBotoesSelecaoRapida=true&conversationId='
        value_field = 'classe_value'
        item_name = "classes"
    elif tree_type == "assunto":
        url = 'https://esaj.tjsp.jus.br/cjpg/assuntoTreeSelect.do?campoId=assunto&mostrarBotoesSelecaoRapida=true&conversationId='
        value_field = 'assunto_value'
        item_name = "assuntos"
    else:
        raise ValueError(f"Invalid tree_type: {tree_type}. Must be 'classe' or 'assunto'")
    
    response = session.get(url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    leaf_items = soup.find_all('li', class_='leafItem')
    
    mapped_items = []
    
    for item in leaf_items:
        # Find span element with searchid attribute inside the li
        span = item.find('span', attrs={'searchid': True})
        if span:
            search_id = span.get('searchid', '')
            text = span.get_text(strip=True)
            
            mapped_items.append({
                value_field: search_id,
                'text': text
            })
    
    try:
        text_to_value = {item['text']: item[value_field] for item in mapped_items}
        
        found_values = []
        not_found = []
        
        for input_item in items:
            if input_item in text_to_value:
                found_values.append(text_to_value[input_item])
            else:
                not_found.append(input_item)
        
        if not_found:
            print(f"Warning: The following {item_name} were not found: {not_found}")
            return None
            
        result_string = "%2C".join(found_values)
        return result_string
        
    except Exception as e:
        logger.error(f"Erro ao extrair {item_name}: %s", str(e))
        raise

# TODO: A função get_magistrados possui uma estrutura diferente das demais. Precisa de mais tempo para investigar.
