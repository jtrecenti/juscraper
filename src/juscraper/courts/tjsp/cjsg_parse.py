"""
Parse de processos da consulta de julgados do segundo grau.
"""
import os
import glob
import re
import logging
import pandas as pd
from tqdm import tqdm
import unidecode
from bs4 import BeautifulSoup

logger = logging.getLogger("juscraper.cjsg_parse")

def cjsg_n_pags(html_source):
    """
    Extrai o número de páginas da consulta CJSG a partir do HTML.
    """
    soup = BeautifulSoup(html_source, "html.parser")
    td_npags = soup.find("td", bgcolor='#EEEEEE')
    if td_npags is None:
        raise ValueError(
            "Não foi possível encontrar o seletor de número de páginas"
            "na resposta HTML. Verifique se a busca retornou resultados"
            "ou se a estrutura da página mudou."
        )
    txt_pag = td_npags.text
    rx = re.compile(r'(?<=de )[0-9]+')
    encontrados = rx.findall(txt_pag)
    if not encontrados:
        raise ValueError(
            "Não foi possível extrair o número de resultados"
            f"da string: {txt_pag}"
        )
    n_results = int(encontrados[0])
    n_pags = n_results // 20 + 1
    return n_pags

def _cjsg_parse_single_page(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    processos = []
    # Itera sobre cada registro de processo (cada <tr> com classe "fundocinza1")
    for tr in soup.find_all('tr', class_='fundocinza1'):
        tds = tr.find_all('td')
        if len(tds) < 2:
            continue
        # O segundo <td> contém os detalhes do processo
        details_td = tds[1]
        details_table = details_td.find('table')
        if not details_table:
            continue

        dados_processo = {}
        # Inicializa ementa como string vazia
        dados_processo['ementa'] = ''
        # Extrai o número do processo (texto do <a> com classes "esajLinkLogin downloadEmenta")
        proc_a = details_table.find('a', class_='esajLinkLogin downloadEmenta')
        if proc_a:
            dados_processo['processo'] = proc_a.get_text(strip=True)
            dados_processo['cd_acordao'] = proc_a.get('cdacordao')
            dados_processo['cd_foro'] = proc_a.get('cdforo')

        # Itera pelas linhas de detalhes (tr com classe "ementaClass2")
        for tr_detail in details_table.find_all('tr', class_='ementaClass2'):
            strong = tr_detail.find('strong')
            if not strong:
                continue
            label = strong.get_text(strip=True)
            # remover acentos
            label = unidecode.unidecode(label)
            # Se for a linha da ementa, trata de forma especial
            if "Ementa:" in label:
                visible_div = None
                # Procura pela div invisível (aquela que possui "display: none" no atributo style)
                for div in tr_detail.find_all('div', align="justify"):
                    style = div.get('style', 'display: none;')
                    if 'display: none' not in style:
                        visible_div = div
                        break
                if visible_div:
                    ementa_text = visible_div.get_text(" ", strip=True)
                    ementa_text = ementa_text.replace("Ementa:", "").strip()
                    dados_processo['ementa'] = ementa_text
                else:
                    # Caso não haja div visível, tenta pegar o texto após 'Ementa:'
                    full_text = tr_detail.get_text(" ", strip=True)
                    ementa_text = full_text.replace("Ementa:", "").strip()
                    dados_processo['ementa'] = ementa_text
            else:
                # Para as demais linhas, extrai o rótulo e o valor
                full_text = tr_detail.get_text(" ", strip=True)
                value = full_text.replace(label, "", 1).strip().lstrip(':').strip()
                key = label.replace(":", "").strip().lower()
                # Normaliza a chave (substitui espaços e caracteres especiais)
                key = key.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                key = key.replace("_de_", "_").replace("_do_", "_")
                if key != 'outros_numeros':
                    # Corrige data_publicacao: remove prefixo se existir
                    if key == 'data_publicacao':
                        value = value.replace('Data de publicação:', '')
                        value = value.replace('Data de Publicação:', '')
                        value = value.strip()
                    dados_processo[key] = value

        processos.append(dados_processo)

    df = pd.DataFrame(processos)
    # Garante que 'ementa' seja a última coluna
    if 'ementa' in df.columns:
        cols = [col for col in df.columns if col != 'ementa'] + ['ementa']
        df = df[cols]
    return df


def cjsg_parse_manager(path: str):
    """
    Parseia os arquivos baixados da segunda instância (cjsg) e
    retorna um DataFrame com as informações dos processos.

    Parameters
    ----------
    path : str
        Caminho do arquivo ou da pasta que contém os arquivos HTML baixados.

    Returns
    -------
    result : pd.DataFrame
        DataFrame com as informações extraídas dos processos.
    """
    if os.path.isfile(path):
        result = [_cjsg_parse_single_page(path)]
    else:
        result = []
        arquivos = glob.glob(f"{path}/**/*.ht*", recursive=True)
        arquivos = [f for f in arquivos if os.path.isfile(f)]
        for file in tqdm(arquivos, desc="Processando documentos"):
            try:
                single_result = _cjsg_parse_single_page(file)
            except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
                logger.error('Error processing %s: %s', file, e)
                continue
            if single_result is not None:
                result.append(single_result)
    return pd.concat(result, ignore_index=True)
