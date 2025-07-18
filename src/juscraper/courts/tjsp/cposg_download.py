"""
Downloads processes from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOSG).
"""
import logging
import os
import time
from urllib.parse import urlparse, parse_qs
from tqdm import tqdm
from bs4 import BeautifulSoup
from ...utils.cnj import clean_cnj, split_cnj, format_cnj

logger = logging.getLogger('juscraper.cposg_download')

def cposg_download_html(id_cnj_list, session, u_base, download_path, sleep_time=0.5):
    """
    Downloads the HTML of one or more processes from the CPOSG.
    Returns a list of paths if list, or a single path if string.
    """
    if isinstance(id_cnj_list, str):
        id_cnj_list = [id_cnj_list]
    paths = []
    for id_cnj in tqdm(id_cnj_list, desc="Baixando processos"):
        id_clean = clean_cnj(id_cnj)
        p = split_cnj(id_clean)
        id_format = format_cnj(id_clean)
        u = f"{u_base}cposg/search.do"
        # 1. Acessar página inicial para garantir cookies válidos
        open_url = f"{u_base}cposg/open.do?gateway=true"
        session.get(open_url)
        # 2. Montar parâmetros corretos
        params = {
            'conversationId': '',
            'paginaConsulta': '1',
            'localPesquisa.cdLocal': '-1',
            'cbPesquisa': 'NUMPROC',
            'tipoNuProcesso': 'UNIFICADO',
            'numeroDigitoAnoUnificado': f"{p['num']}-{p['dv']}.{p['ano']}",
            'foroNumeroUnificado': p['orgao'],
            'dePesquisaNuUnificado': id_format,
            'dePesquisa': '',
            'uuidCaptcha': '',
            'pbEnviar': 'Pesquisar'
        }
        r = session.get(u, params=params)
        soup = BeautifulSoup(r.text, 'html.parser')
        path = f"{download_path}/cposg/{id_clean}"
        if not os.path.isdir(path):
            os.makedirs(path)
        # 3. Tratar tipos de resposta
        # Caso 1: listagem de processos
        if soup.find('div', id='listagemDeProcessos'):
            links = [a['href'] for a in soup.select('a.linkProcesso')]
            for link in links:
                codigo = parse_qs(urlparse(link).query).get('processo.codigo', [None])[0]
                show_url = f"{u_base}cposg/show.do?processo.codigo={codigo}"
                r_show = session.get(show_url)
                file_name = f"{path}/{id_clean}_cd_processo_{codigo}.html"
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(r_show.text)
        # Caso 2: incidentes/modal
        elif soup.find('div', id='modalIncidentes'):
            codigos = [i['value'] for i in soup.select('input#processoSelecionado')]
            for codigo in codigos:
                show_url = f"{u_base}cposg/show.do?processo.codigo={codigo}"
                r_show = session.get(show_url)
                file_name = f"{path}/{id_clean}_cd_processo_{codigo}.html"
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(r_show.text)
        # Caso 3: resposta simples
        else:
            codigo = None
            input_cd = soup.find('input', {'name': 'cdProcesso'})
            if input_cd:
                codigo = input_cd.get('value')
            file_name = f"{path}/{id_clean}_cd_processo_{codigo or 'simples'}.html"
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(r.text)
        paths.append(path)
        time.sleep(sleep_time)
    return paths if len(paths) > 1 else paths[0]

def cposg_download_api(id_cnj_list, session, api_base, download_path, sleep_time=0.5):
    """
    Downloads the JSON of one or more processes from the CPOSG via API.
    """
    if isinstance(id_cnj_list, str):
        id_cnj_list = [id_cnj_list]
    paths = []
    endpoint = 'processo/cposg/search/numproc/'
    for id_cnj in tqdm(id_cnj_list, desc="Baixando processos"):
        id_clean = clean_cnj(id_cnj)
        u = f"{api_base}{endpoint}{id_clean}"
        path = f"{download_path}/cposg/{id_clean}"
        if not os.path.isdir(path):
            os.makedirs(path)
        r = session.get(u)
        if r.status_code != 200:
            raise RuntimeError(f"A consulta à API falhou. Status code {r.status_code}.")
        with open(f"{path}/{id_clean}.json", 'w', encoding='utf-8') as f:
            f.write(r.text)
        paths.append(path)
        time.sleep(sleep_time)
    return paths if len(paths) > 1 else paths[0]
