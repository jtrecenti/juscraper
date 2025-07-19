"""
Download of results from the TJSP Consulta de Julgados de Segundo Grau (CJSG).
"""
import os
import time
from datetime import datetime
import logging
import requests
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger("juscraper.cjsg_download")

def cjsg_download(
    pesquisa: str,
    download_path: str,
    u_base: str,
    sleep_time: float = 0.5,
    verbose: int = 1,
    ementa: str = None,
    classe: str = None,
    assunto: str = None,
    comarca: str = None,
    orgao_julgador: str = None,
    data_inicio: str = None,
    data_fim: str = None,
    baixar_sg: bool = True,
    tipo_decisao: str = 'acordao',
    paginas: range = None,
    get_n_pags_callback=None
):
    """
    Downloads HTML files from the CJSG search results pages.

    Args:
        pesquisa (str): Search term.
        download_path (str): Base directory for saving files.
        u_base (str): ESAJ base URL.
        sleep_time (float): Time to wait between requests.
        verbose (int): Logging level.
        ementa, classe, assunto, comarca, orgao_julgador, data_inicio, data_fim: Optional filters.
        baixar_sg (bool): If True, also downloads from the second stage.
        tipo_decisao (str): 'acordao' or 'monocratica'.
        paginas (range): Page range to download.
        get_n_pags_callback (callable): Callback function to extract number of pages from HTML.
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    _ = WebDriverWait(driver, 10)
    driver.get(f"{u_base}cjsg/consultaCompleta.do")
    driver.find_element(By.NAME, 'dados.buscaInteiroTeor').send_keys(pesquisa)
    time.sleep(0.5)
    if ementa:
        driver.find_element(By.NAME, 'dados.ementa').send_keys(ementa)
        time.sleep(0.5)
    if classe:
        driver.find_element(By.NAME, 'dados.classe').send_keys(classe)
        time.sleep(0.5)
    if assunto:
        driver.find_element(By.NAME, 'dados.assunto').send_keys(assunto)
        time.sleep(0.5)
    if comarca:
        driver.find_element(By.NAME, 'dados.comarca').send_keys(comarca)
        time.sleep(0.5)
    if orgao_julgador:
        driver.find_element(By.NAME, 'dados.orgaoJulgador').send_keys(orgao_julgador)
        time.sleep(0.5)
    if data_inicio:
        driver.find_element(By.NAME, 'dados.dtJulgamentoInicio').send_keys(data_inicio)
        time.sleep(0.5)
    if data_fim:
        driver.find_element(By.NAME, 'dados.dtJulgamentoFim').send_keys(data_fim)
        time.sleep(0.5)
    if not baixar_sg:
        driver.find_element(By.ID, 'origem2grau').click()
        time.sleep(0.25)
        driver.find_element(By.ID, 'origemRecursal').click()
        time.sleep(0.25)
    driver.find_element(By.ID, 'pbSubmit').click()
    time.sleep(1)
    if get_n_pags_callback is None:
        raise ValueError(
            'É necessário fornecer get_n_pags_callback para extrair o número de páginas.'
        )
    # Checagem de erro/filtro/ausência de resultados
    try:
        n_pags = get_n_pags_callback(driver.page_source)
    except Exception as e:
        # Salvar HTML bruto para debug
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        debug_dir = os.path.join(download_path, "cjsg_debug")
        if not os.path.isdir(debug_dir):
            os.makedirs(debug_dir)
        debug_file = os.path.join(debug_dir, f"cjsg_primeira_pagina_{timestamp}.html")
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        logger.error(
            'Erro ao extrair número de páginas: %s. HTML salvo em: %s',
            str(e),
            debug_file
        )
        driver.quit()
        raise ValueError(
            f"Erro ao extrair número de páginas: {e}. HTML salvo em: {debug_file}"
        ) from e
    if paginas is None:
        paginas = range(1, n_pags + 1)
    if max(paginas) > n_pags:
        pag_min = min(paginas)
        paginas = range(pag_min, n_pags + 1)
    if verbose > 0:
        logger.info("Total de páginas: %s", n_pags)
        logger.info("Paginas a serem baixadas: %s", list(paginas))
    cookies = driver.get_cookies()
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'])
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = f"{download_path}/cjsg/{timestamp}"
    if not os.path.isdir(path):
        os.makedirs(path)
    for pag in tqdm(paginas, desc="Baixando documentos"):
        time.sleep(sleep_time)
        query = {
            'tipoDeDecisao': 'A' if tipo_decisao == 'acordao' else 'D',
            'pagina': pag + 1,
            'conversationId': ''
        }
        u = f"{u_base}cjsg/trocaDePagina.do"
        r = session.get(u, params=query)
        file_name = f"{path}/cjsg_{pag + 1:05d}.html"
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(r.text)
    driver.quit()
    return path
