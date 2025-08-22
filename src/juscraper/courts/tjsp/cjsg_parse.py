"""
Parse of cases from the TJSP Consulta de Julgados de Segundo Grau (CJSG).
"""
import glob
import logging
import os
import re

import pandas as pd
import unidecode
from bs4 import BeautifulSoup
from tqdm import tqdm

logger = logging.getLogger("juscraper.cjsg_parse")


class RecaptchaDetectedError(Exception):
    """Raised when reCAPTCHA protection is detected on TJSP page."""

def cjsg_n_pags(html_source):
    """
    Extracts the number of pages from the CJSG search results HTML.

    Raises:
        RecaptchaDetectedError: If reCAPTCHA protection is detected.
        ValueError: If page structure is unexpected or no results found.
    """
    soup = BeautifulSoup(html_source, "html.parser")

    # Check for reCAPTCHA detection message
    recaptcha_message = soup.find("td", id="mensagemRetorno")
    if recaptcha_message:
        message_text = recaptcha_message.get_text(strip=True)
        if "reCAPTCHA" in message_text and "robô" in message_text:
            raise RecaptchaDetectedError(
                f"reCAPTCHA detectado pelo TJSP: {message_text}\n\n"
                "💡 O site identificou acesso automatizado. Como resolver:\n"
                "1️⃣ Aguarde 5-10 minutos antes de tentar novamente\n"
                "2️⃣ Aumente o sleep_time no seu código:\n"
                "   - tjsp.cjsg('sua busca', sleep_time=3.0)  # 3 segundos entre requests\n"
                "   - ou tjsp.cjsg('sua busca', sleep_time=5.0)  # 5 segundos (mais seguro)\n"
                "3️⃣ Faça menos consultas simultâneas\n"
                "4️⃣ Considere fazer uma consulta manual no site primeiro para 'aquecer' a sessão"
            )

    td_npags = soup.find("td", bgcolor='#EEEEEE')
    if td_npags is None:
        raise ValueError(
            "Não foi possível encontrar o seletor de número de páginas "
            "na resposta HTML. Verifique se a busca retornou resultados "
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
    Parses the downloaded files from the CJSG search results.
    Returns a DataFrame with the information of the processes.

    Parameters
    ----------
    path : str
        Path to the file or directory containing the downloaded HTML files.

    Returns
    -------
    result : pd.DataFrame
        DataFrame with the extracted information of the processes.
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
