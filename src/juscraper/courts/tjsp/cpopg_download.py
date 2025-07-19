"""
Downloads of processes from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
"""
import os
import time
from urllib.parse import urlparse, parse_qs
import logging
import requests
from tqdm import tqdm
from ...utils.cnj import clean_cnj, split_cnj, format_cnj

logger = logging.getLogger('juscraper.cpopg_download')

def cpopg_download_html(
    id_cnj_list,
    session,
    u_base,
    download_path,
    sleep_time=0.5,
    get_links_callback=None
):
    """
    Downloads processes in HTML from the TJSP Consulta de Processos Originários do Primeiro Grau (CPOPG).
    id_cnj_list: list of CNJs
    session: requests.Session authenticated
    u_base: base URL of ESAJ
    download_path: base directory to save
    sleep_time: interval between attempts
    get_links_callback: function to extract links from HTML
    """
    n_items = len(id_cnj_list)
    for idp in tqdm(id_cnj_list, total=n_items, desc="Baixando processos"):
        try:
            cpopg_download_html_single(
                idp,
                session,
                u_base,
                download_path,
                sleep_time,
                get_links_callback
            )
        except (OSError, UnicodeDecodeError, ValueError,
                AttributeError, requests.RequestException) as e:
            logger.error(
                "Erro ao baixar o processo %s: %s",
                idp,
                e
            )
            continue

def cpopg_download_html_single(
    id_cnj,
    session,
    u_base,
    download_path,
    sleep_time=0.5,
    get_links_callback=None
):
    """
    Downloads a process in HTML from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
    id_cnj: CNJ of the process
    session: requests.Session authenticated
    u_base: base URL of ESAJ
    download_path: base directory to save
    sleep_time: interval between attempts
    get_links_callback: function to extract links from HTML
    """
    id_clean = clean_cnj(id_cnj)
    path = f"{download_path}/cpopg/{id_clean}"
    logger.info("Salvando em %s", path)
    if not os.path.isdir(path):
        os.makedirs(path)
    for file in os.listdir(path):
        if file.endswith('.html'):
            logger.info("O processo %s ja foi baixado.", id_clean)
            return path
    time.sleep(sleep_time)
    id_format = format_cnj(id_clean)
    p = split_cnj(id_clean)
    u = f"{u_base}cpopg/search.do"
    parms = {
        'conversationId': '',
        'cbPesquisa': 'NUMPROC',
        'numeroDigitoAnoUnificado': f"{p['num']}-{p['dv']}.{p['ano']}",
        'foroNumeroUnificado': p['orgao'],
        'dadosConsulta.valorConsultaNuUnificado': id_format,
        'dadosConsulta.valorConsulta': '',
        'dadosConsulta.tipoNuProcesso': 'UNIFICADO'
    }
    for _ in range(5):
        try:
            r = session.get(u, params=parms)
            if get_links_callback is None:
                raise RuntimeError(
                    "get_links_callback precisa ser"
                    "fornecido para extrair links do HTML."
                )
            links = get_links_callback(r)
            cd_processo = []
            for link in links:
                query_params = parse_qs(urlparse(link).query)
                codigo = query_params.get('processo.codigo', [None])[0]
                cd_processo.append(codigo)
            if len(links) == 0:
                logger.error("Nenhum link encontrado para o processo %s.", id_clean)
                raise RuntimeError(
                    f"Nenhum link encontrado para o processo {id_clean}."
                )
            elif len(links) == 1:
                file_name = f"{path}/{id_clean}_{cd_processo[0]}.html"
                logger.info("Salvando em %s", file_name)
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(r.text)
            else:
                for index, link in enumerate(links):
                    u2 = f"{u_base}{link}"
                    r2 = session.get(u2)
                    if r2.status_code != 200:
                        raise requests.HTTPError(
                            f"A consulta ao site falhou."
                            f"Processo: {id_clean}; Código: {cd_processo[index]},"
                            f"Status code {r2.status_code}."
                        )
                    file_name = f"{path}/{id_clean}_{cd_processo[index]}.html"
                    logger.info("Salvando em %s", file_name)
                    with open(file_name, 'w', encoding='utf-8') as f:
                        f.write(r2.text)
            break
        except (OSError, UnicodeDecodeError, ValueError,
                AttributeError, requests.RequestException) as e:
            logger.error(
                "Erro ao conectar ao site (processo %s)."
                "Tentando novamente em %.1f segundos. (%s)",
                id_cnj,
                sleep_time,
                e
            )
            time.sleep(sleep_time)
    return path

def cpopg_download_api(
    id_cnj_list,
    session,
    api_base,
    download_path
):
    """
    Downloads processes in JSON from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
    id_cnj_list: list of CNJs
    session: requests.Session authenticated
    api_base: base URL of ESAJ API
    download_path: base directory to save
    """
    n_items = len(id_cnj_list)
    for idp in tqdm(id_cnj_list, total=n_items, desc="Baixando processos"):
        try:
            cpopg_download_api_single(idp, session, api_base, download_path)
        except (OSError, UnicodeDecodeError, ValueError,
                AttributeError, requests.RequestException) as e:
            logger.error(
                "Erro ao baixar o processo %s: %s",
                idp,
                e
            )
            continue

def cpopg_download_api_single(
    id_cnj,
    session,
    api_base,
    download_path
):
    """
    Downloads a process in JSON from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
    id_cnj: CNJ of the process
    session: requests.Session authenticated
    api_base: base URL of ESAJ API
    download_path: base directory to save
    """
    endpoint = 'processo/cpopg/search/numproc/'
    id_clean = clean_cnj(id_cnj)
    u = f"{api_base}{endpoint}{id_clean}"
    path = f"{download_path}/cpopg/{id_clean}"
    if not os.path.isdir(path):
        os.makedirs(path)
    r = session.get(u)
    if r.status_code != 200:
        raise requests.HTTPError(
            f"A consulta à API falhou."
            f"Status code {r.status_code}."
        )
    with open(f"{path}/{id_clean}.json", 'w', encoding='utf-8') as f:
        f.write(r.text)
    json_response = r.json()
    if not json_response:
        logger.error("Nenhum dado encontrado para o processo %s.", id_clean)
        return ''
    for processo in json_response:
        cd_processo = processo['cdProcesso']
        endpoint_basicos = 'processo/cpopg/dadosbasicos/'
        u_basicos = f"{api_base}{endpoint_basicos}{cd_processo}"
        r_basicos = session.post(u_basicos, json={'cdProcesso': cd_processo})
        if r_basicos.status_code != 200:
            raise requests.HTTPError(
                f"A consulta à API falhou."
                f"Status code {r_basicos.status_code}."
            )
        with open(f"{path}/{cd_processo}_basicos.json", 'w', encoding='utf-8') as f:
            f.write(r_basicos.text)
        componentes = ['partes', 'movimentacao', 'incidente', 'audiencia']
        for comp in componentes:
            endpoint_comp = f"processo/cpopg/{comp}/{cd_processo}"
            r_comp = session.get(f"{api_base}{endpoint_comp}")
            if r_comp.status_code == 200:
                with open(f"{path}/{cd_processo}_{comp}.json", 'w', encoding='utf-8') as f:
                    f.write(r_comp.text)
            else:
                raise requests.HTTPError(
                    f"Erro ao buscar {comp} para o processo {cd_processo}."
                    f"Status: {r_comp.status_code}"
                )
    return path
