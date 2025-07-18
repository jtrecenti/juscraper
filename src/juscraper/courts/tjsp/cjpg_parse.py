"""
Parse of cases from the TJSP jurisprudence search.
"""
import os
import re
import glob
import logging
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup

logger = logging.getLogger("juscraper.cjpg_parse")

def cjpg_n_pags(page_source):
    """
    Extracts the number of pages from the Cjpg search results HTML.
    """
    soup = BeautifulSoup(page_source, "html.parser")
    page_element = soup.find(attrs={'bgcolor': '#EEEEEE'})
    if page_element is None:
        raise ValueError(
            "Não foi possível encontrar o seletor de número de páginas"
            "na resposta HTML. Verifique se a busca retornou resultados"
            "ou se a estrutura da página mudou."
        )
    match = re.search(r'\d+$', page_element.get_text().strip())
    if match is None:
        raise ValueError(
            "Não foi possível extrair o número de resultados"
            f"da string: {page_element.get_text().strip()}"
        )
    results = int(match.group())
    pags = results // 10 + 1
    return pags

def cjpg_parse_single(path):
    """
    Parses a downloaded HTML file from the cjpg_download function.
    """
    with open(path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    processos = []
    div_dados_resultado = soup.find('div', {'id': 'divDadosResultado'})
    if div_dados_resultado:
        tr_processos = div_dados_resultado.find_all('tr', class_='fundocinza1')
        for tr_processo in tr_processos:
            dados_processo = {}
            tabela_dados = tr_processo.find('table')
            # id_processo
            link_inteiro_teor = tabela_dados.find('a', {'style': 'vertical-align: top'})
            if link_inteiro_teor:
                if link_inteiro_teor.get('name'):
                    dados_processo['cd_processo'] = link_inteiro_teor.get('name').split('-')[0]
                else:
                    dados_processo['cd_processo'] = None
                if link_inteiro_teor.find('span', class_='fonteNegrito'):
                    dados_processo['id_processo'] = link_inteiro_teor.find(
                        'span', class_='fonteNegrito'
                    ).text.strip()
                else:
                    dados_processo['id_processo'] = None
            # Outros campos
            linhas_detalhes = tabela_dados.find_all('tr', class_='fonte')
            for linha in linhas_detalhes:
                strong = linha.find('strong')
                if strong:
                    texto = linha.text.strip()
                    chave, valor = texto.split(':', 1)
                    chave = chave.strip().lower().replace(' ', '_').replace('-','')
                    valor = valor.strip()
                    if chave == 'data_de_disponibilização':
                        chave = 'data_disponibilizacao'
                    dados_processo[chave] = valor
            # Decisão
            div_decisao = tabela_dados.find('div', {'align': 'justify', 'style': 'display: none;'})
            if div_decisao:
                spans = div_decisao.find_all('span')
                if spans:
                    decisao_text = spans[-1].get_text(separator=" ", strip=True)
                else:
                    decisao_text = ''
                dados_processo['decisao'] = decisao_text
            processos.append(dados_processo)
    return pd.DataFrame(processos)

def cjpg_parse_manager(path):
    """
    Parses the downloaded files from the cjpg_download function.
    Returns a DataFrame with the information of the processes.
    """
    if os.path.isfile(path):
        result = [cjpg_parse_single(path)]
    else:
        result = []
        arquivos = glob.glob(f"{path}/**/*.ht*", recursive=True)
        arquivos = [f for f in arquivos if os.path.isfile(f)]
        for file in tqdm(arquivos, desc="Processando documentos"):
            if os.path.isfile(file):
                try:
                    single_result = cjpg_parse_single(file)
                except (ValueError, OSError) as e:
                    logger.error('Error processing %s: %s', file, e)
                    single_result = None
                    continue
                if single_result is not None:
                    result.append(single_result)
    result = pd.concat(result, ignore_index=True)
    return result
