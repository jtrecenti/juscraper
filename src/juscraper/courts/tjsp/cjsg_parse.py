"""
Parse of cases from the TJSP Consulta de Julgados de Segundo Grau (CJSG).
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
    Extracts the number of pages from the CJSG search results HTML.
    """
    soup = BeautifulSoup(html_source, "html.parser")
    
    # Check if there are no results
    page_text = soup.get_text().lower()
    if 'nenhum resultado' in page_text or 'não foram encontrados' in page_text or 'sem resultados' in page_text:
        return 0
    
    # Check for error messages or captcha issues
    # Only check for specific error elements, not just the word "erro" in the text
    # (which could be part of a decision content)
    error_divs = soup.find_all(['div', 'span', 'p'], class_=re.compile(r'error|erro|mensagem.*erro', re.I))
    if error_divs:
        # Check if it's a captcha error
        error_text = ' '.join([elem.get_text().lower() for elem in error_divs[:3]])
        if 'captcha' in error_text or 'verificação' in error_text:
            raise ValueError(
                "Captcha não foi resolvido. A página pode requerer verificação manual."
            )
        # Only raise error if we found actual error elements (not just "erro" in content)
        error_msg = ' '.join([elem.get_text() for elem in error_divs[:3]])
        if error_msg.strip():  # Only raise if there's actual error message content
            raise ValueError(
                f"Erro detectado na página: {error_msg[:200]}"
            )
    
    # Try to find pagination element following R code logic
    # R code: xml_find_all(xpath = "//td[contains(., 'Resultados')]")
    # Then extract number from end: str_extract("\\d+$")
    td_npags = None
    
    # First try: look for td containing "Resultados" (as in R code)
    all_tds = soup.find_all("td")
    for td in all_tds:
        td_text = td.get_text()
        if 'Resultados' in td_text or 'resultados' in td_text.lower():
            td_npags = td
            break
    
    # Second try: look for td with bgcolor='#EEEEEE' (original approach)
    if td_npags is None:
        td_npags = soup.find("td", bgcolor='#EEEEEE')
    
    # Third try: look for pagination text
    if td_npags is None:
        td_npags = soup.find("td", class_=re.compile(r'.*pag.*', re.I))
    
    # Fourth try: find by text content
    if td_npags is None:
        for td in all_tds:
            td_text = td.get_text().lower()
            if 'página' in td_text and ('de' in td_text or 'total' in td_text):
                td_npags = td
                break
    
    if td_npags is None:
        # Check if results table exists
        results_table = soup.find("table", class_=re.compile(r'fundocinza|resultado', re.I))
        if results_table is None:
            # Check if we're still on the form page
            if soup.find("form", id=re.compile(r'form|consulta', re.I)):
                raise ValueError(
                    "Ainda na página de consulta. O formulário pode não ter sido submetido corretamente."
                )
            raise ValueError(
                "Não foi possível encontrar o seletor de número de páginas "
                "na resposta HTML. Verifique se a busca retornou resultados "
                "ou se a estrutura da página mudou."
            )
        # If table exists but no pagination, assume 1 page
        return 1
    
    txt_pag = td_npags.get_text()
    
    # Try R code approach: extract number from end of text (\\d+$)
    rx_end = re.compile(r'\d+$')
    encontrados = rx_end.findall(txt_pag.strip())
    
    if not encontrados:
        # Try original approach: (?<=de )[0-9]+
        rx = re.compile(r'(?<=de )[0-9]+')
        encontrados = rx.findall(txt_pag)
    
    if not encontrados:
        # Try alternative regex patterns
        rx2 = re.compile(r'[0-9]+(?=\s*(?:resultado|registro|página))', re.I)
        encontrados = rx2.findall(txt_pag)
    
    if not encontrados:
        # Try to find any number in the text
        rx3 = re.compile(r'\d+')
        encontrados = rx3.findall(txt_pag)
        # Take the largest number (likely the total)
        if encontrados:
            encontrados = [max(encontrados, key=int)]
    
    if not encontrados:
        raise ValueError(
            "Não foi possível extrair o número de resultados da paginação. "
            f"Formato inesperado encontrado. Texto: {txt_pag[:100]}"
        )
    
    n_results = int(encontrados[0])
    # R code: divide_by(20) then ceiling()
    n_pags = (n_results + 19) // 20  # Equivalent to math.ceil(n_results / 20)
    return n_pags

def _cjsg_parse_single_page(path: str):
    # Read file - try both encodings to handle both test files (utf-8) and real downloads (latin1)
    with open(path, 'rb') as f:
        raw_content = f.read()
    
    # Try utf-8 first (for test files), then latin1 (for real downloads)
    try:
        content = raw_content.decode('utf-8')
    except UnicodeDecodeError:
        # If utf-8 fails, try latin1 (as saved from website)
        try:
            content = raw_content.decode('latin1')
        except UnicodeDecodeError:
            # Last resort: decode with errors='replace'
            content = raw_content.decode('utf-8', errors='replace')
    
    soup = BeautifulSoup(content, 'html.parser')

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
            # Se for a linha da ementa, trata de forma especial
            # Check before applying unidecode to preserve original text
            if "Ementa:" in label or "ementa:" in label.lower():
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
                # Remove soft hyphens and other invisible characters
                value = value.replace('\xad', '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
                # Normaliza a chave: remove acentos e caracteres especiais
                key = label.replace(":", "").strip().lower()
                # Apply unidecode to normalize accents
                key_normalized = unidecode.unidecode(key)
                # Normaliza a chave (substitui espaços e caracteres especiais)
                key_normalized = key_normalized.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                key_normalized = key_normalized.replace("_de_", "_").replace("_do_", "_")
                # Remove múltiplos underscores consecutivos
                import re
                key_normalized = re.sub(r'_+', '_', key_normalized)
                key_normalized = key_normalized.strip('_')
                
                if key_normalized != 'outros_numeros':
                    # Corrige nomes específicos de colunas
                    if 'data_publicacao' in key_normalized or 'data_publicassapso' in key_normalized:
                        key_normalized = 'data_publicacao'
                        value = value.replace('Data de publicação:', '')
                        value = value.replace('Data de Publicação:', '')
                        value = value.replace('Data de publicassapso:', '')
                        value = value.strip()
                    elif 'orgao_julgador' in key_normalized or 'argapso_julgador' in key_normalized:
                        key_normalized = 'orgao_julgador'
                        value = value.replace('Órgão julgador:', '')
                        value = value.replace('Orgão julgador:', '')
                        value = value.replace('argapso julgador:', '')
                        value = value.strip()
                    
                    dados_processo[key_normalized] = value

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
    if not result:
        return pd.DataFrame()
    return pd.concat(result, ignore_index=True)
