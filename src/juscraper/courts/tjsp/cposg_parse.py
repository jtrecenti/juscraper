"""
Download de processos da consulta de processos
originários do primeiro grau (CPOSG) do TJSP.
"""
import glob
import os
import re
import logging
from bs4 import BeautifulSoup
from tqdm import tqdm
import pandas as pd

logger = logging.getLogger('juscraper.cposg_parse')

def cposg_parse(path: str):
    """
    Parse all HTML files in the given directory.
    """
    arquivos = glob.glob(os.path.join(path, '**/*.html'), recursive=True)
    dados = []
    for arq in tqdm(arquivos, total=len(arquivos), desc="Processando arquivos"):
        try:
            linhas = cposg_parse_single_html(arq)
            dados.extend(linhas)
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
            logger.error("Erro ao processar %s: %s", arq, e)
    if not dados:
        return pd.DataFrame()
    df = pd.DataFrame(dados)
    return df

def cposg_parse_manager(path: str):
    """
    Standalone parse manager for CPOSG HTML files. Returns a DataFrame with parsed data.
    """
    arquivos = glob.glob(os.path.join(path, '**/*.html'), recursive=True)
    dados = []
    for arq in tqdm(arquivos, total=len(arquivos), desc="Processando arquivos"):
        try:
            linhas = cposg_parse_single_html(arq)
            dados.extend(linhas)
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
            logger.error("Erro ao processar %s: %s", arq, e)
    if not dados:
        return pd.DataFrame()
    df = pd.DataFrame(dados)
    return df

def cposg_parse_single_json(path: str):
    """Stub para evitar erro de importação."""
    raise NotImplementedError("cposg_parse_single_json ainda não implementado.")

def cposg_parse_single_html(html_path):
    """
    Parse a single HTML document from CPOSG.
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    soup = BeautifulSoup(html_content, 'html.parser')
    # Validate if the HTML contains expected content
    # Check if it's a double process
    if soup.select('.linkProcesso'):
        return []
    # Check if it has movement table
    if not soup.find(id='tabelaTodasMovimentacoes'):
        return []
    # Initialize result object (will be converted to a single row)
    result = {}
    # Extract ID original (process number from URL)
    id_link = soup.select_one("a[href*='processo.codigo']")
    if id_link:
        result['id_original'] = id_link.get_text(strip=True)
    # Extract main process number and status
    # Process number
    processo_tag = soup.select_one('span.unj-larger')
    if processo_tag:
        result['processo'] = processo_tag.get_text(strip=True)
    # Status from tags
    status_tags = soup.select('span.unj-tag')
    if status_tags:
        status_text = ' / '.join([tag.get_text(strip=True) for tag in status_tags])
        result['status'] = status_text
    # Map of label texts to field names in the result
    field_mapping = {
        'classe': 'classe',
        'assunto': 'assunto',
        'seção': 'secao',
        'órgão julgador': 'orgao_julgador',
        'área': 'area',
        'relator': 'relator',
        'valor da ação': 'valor_da_acao',
        'origem': 'origem',
        'volumes / apensos': 'volume_apenso'
    }
    # Direct extraction from labels - this is more reliable than using CSS selectors
    for div in soup.find_all('div'):
        # Find label spans
        label_span = div.find('span', class_='unj-label')
        if not label_span:
            continue
        label_text = label_span.get_text(strip=True).lower()
        # Get the value that follows the label
        value_div = div.find('div')
        if not value_div:
            continue
        value = value_div.get_text(strip=True)
        # Map to the correct field name if it exists in our mapping
        for key, field_name in field_mapping.items():
            if key in label_text:
                result[field_name] = value
                break
    # Extract movements
    movs = []
    movs_table = soup.find(id='tabelaTodasMovimentacoes')
    if movs_table:
        for row in movs_table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2 and cells[0].get_text(strip=True):  # Skip empty rows
                data = cells[0].get_text(strip=True)
                movimento_text = cells[1].get_text(strip=True)
                # Split movimento into movimento and descricao like R does
                parts = movimento_text.split('\n', 1)
                movimento = parts[0].strip() if parts else ""
                descricao = parts[1].strip() if len(parts) > 1 else ""

                movs.append({
                    'data': data,
                    'movimento': movimento,
                    'descricao': descricao
                })
    result['movimentacoes'] = movs

    # Extract parties
    partes = []
    partes_table = soup.find(id='tableTodasPartes') or soup.find(id='tablePartesPrincipais')
    if partes_table and not soup.find(string=re.compile("Não há Partes")):
        for i, row in enumerate(partes_table.find_all('tr')):
            cells = row.find_all('td')
            if len(cells) >= 2:
                parte = cells[0].get_text(strip=True)
                papeis_text = cells[1].get_text(strip=True)

                # Clean parte similar to R's implementation
                parte_clean = re.sub(r'[^a-zA-Z]', '', parte)

                # Split and process papeis like R does
                papeis = papeis_text.split('\t')
                for papel in papeis:
                    papel = papel.strip()
                    if not papel:
                        continue

                    papel_clean = papel.replace('&nbsp', ' ')
                    nome_match = re.search(r'(?<=:)\s*([^:]+)$', papel_clean)
                    papel_match = re.search(r'^([^:]+)(?=:)', papel_clean)

                    nome = nome_match.group(1).strip() if nome_match else None
                    papel_tipo = papel_match.group(1).strip() if papel_match else parte_clean

                    if nome:
                        partes.append({
                            'id_parte': i + 1,
                            'nome': nome,
                            'parte': parte_clean,
                            'papel': papel_tipo
                        })
    result['partes'] = partes

    # Extract history
    hist = []
    hist_table = soup.find(id='tdHistoricoDeClasses')
    if hist_table:
        for row in hist_table.find_all('tr'):
            cells = row.find_all('td')
            if cells:
                row_data = [cell.get_text(strip=True) for cell in cells]
                hist.append(row_data)
    result['historico'] = hist

    # Extract decisions and composition
    tables = soup.select("table[style='margin-left:15px; margin-top:1px;']")

    # Judgments
    decisoes = []
    judgment_table_idx = -1
    for i, table in enumerate(tables):
        if "Situação do julgamento" in table.get_text():
            judgment_table_idx = i
            break

    if judgment_table_idx >= 0 and judgment_table_idx + 1 < len(tables):
        for table in tables[judgment_table_idx + 1:]:
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # Try to parse date - this is a simplified version
                    data = cells[0].get_text(strip=True)
                    situacao = cells[1].get_text(strip=True)
                    decisao = cells[2].get_text(strip=True)

                    # Skip rows without valid data
                    if data and not data.isalpha():
                        decisoes.append({
                            'data': data,
                            'situacao': situacao,
                            'decisao': decisao
                        })
    result['decisoes'] = decisoes

    # Composition
    composicao = []
    composition_table_idx = -1
    for i, table in enumerate(tables):
        if table.get_text().strip().startswith("Relator"):
            composition_table_idx = i
            break

    if composition_table_idx >= 0:
        for row in tables[composition_table_idx].find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                participacao = cells[0].get_text(strip=True)
                magistrado = cells[1].get_text(strip=True)

                if participacao:
                    composicao.append({
                        'participacao': participacao,
                        'magistrado': magistrado
                    })
                    # Also use this to populate the relator field if it's empty
                    if participacao == "Relator" and not result.get('relator'):
                        result['relator'] = magistrado
    result['composicao'] = composicao

    # First instance
    primeira_inst = []
    first_instance_table_idx = -1
    for i, table in enumerate(tables):
        if "Nº de 1ª instância" in table.get_text():
            first_instance_table_idx = i
            break

    if first_instance_table_idx >= 0 and first_instance_table_idx + 1 < len(tables):
        # If we have the data table
        data_table = tables[first_instance_table_idx + 1]
        for row in data_table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 5:
                primeira_inst.append({
                    'id_1a_inst': cells[0].get_text(strip=True),
                    'foro': cells[1].get_text(strip=True),
                    'vara': cells[2].get_text(strip=True),
                    'juiz': cells[3].get_text(strip=True),
                    'obs': cells[4].get_text(strip=True)
                })
    result['primeira_inst'] = primeira_inst

    # Ensure all required fields are present
    required_fields = [
        'processo', 'status', 'classe', 'assunto', 'secao', 'orgao_julgador',
        'area', 'relator', 'valor_da_acao', 'origem', 'volume_apenso',
        'id_original', 'movimentacoes', 'partes', 'historico', 'decisoes',
        'composicao', 'primeira_inst'
    ]

    for field in required_fields:
        if field not in result:
            result[field] = None

    # Attempt to extract values from the full HTML if any are still missing
    if not result.get('classe'):
        classe_match = re.search(r'Classe:\s*([^<]+)', html_content)
        if classe_match:
            result['classe'] = classe_match.group(1).strip()

    if not result.get('assunto'):
        assunto_match = re.search(r'Assunto:\s*([^<]+)', html_content)
        if assunto_match:
            result['assunto'] = assunto_match.group(1).strip()

    # Try a more aggressive approach for all fields
    for label, field in field_mapping.items():
        if not result.get(field):
            # Try to find it in text
            pattern = fr"{label.capitalize()}:\s*([^<\n]+)"
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                result[field] = match.group(1).strip()

    # Return a single row (dictionary) matching the structure of the R output
    return [result]
