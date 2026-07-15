"""
Parses downloaded files from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOSG).
"""
import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

logger = logging.getLogger('juscraper.cposg_parse')

_FIELD_MAPPING = (
    ('classe', 'classe'),
    ('assunto', 'assunto'),
    ('seção', 'secao'),
    ('órgão julgador', 'orgao_julgador'),
    ('área', 'area'),
    ('relator', 'relator'),
    ('valor da ação', 'valor_da_acao'),
    ('origem', 'origem'),
    ('volumes / apensos', 'volume_apenso'),
)

_REQUIRED_FIELDS = (
    'processo',
    'status',
    'classe',
    'assunto',
    'secao',
    'orgao_julgador',
    'area',
    'relator',
    'valor_da_acao',
    'origem',
    'volume_apenso',
    'id_original',
    'movimentacoes',
    'partes',
    'historico',
    'decisoes',
    'composicao',
    'primeira_inst',
)

_DETAIL_TABLE_STYLE = 'margin-left:15px; margin-top:1px;'


def cposg_parse(path: str):
    """
    Parses all HTML files in the given directory.
    """
    arquivos = list(Path(path).rglob('*.html'))
    dados = []
    for arq in tqdm(arquivos, total=len(arquivos), desc="Processando arquivos"):
        try:
            linhas = cposg_parse_single_html(arq)
            dados.extend(linhas)
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
            logger.error("Erro ao processar %s: %s", arq, e)
    if not dados:
        return pd.DataFrame()
    return pd.DataFrame(dados)


def cposg_parse_manager(path: str):
    """
    Standalone parse manager for CPOSG HTML files. Returns a DataFrame with parsed data.
    """
    arquivos = list(Path(path).rglob('*.html'))
    dados = []
    for arq in tqdm(arquivos, total=len(arquivos), desc="Processando arquivos"):
        try:
            linhas = cposg_parse_single_html(arq)
            dados.extend(linhas)
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
            logger.error("Erro ao processar %s: %s", arq, e)
    if not dados:
        return pd.DataFrame()
    return pd.DataFrame(dados)


def cposg_parse_single_json(path: str):
    """Stub to avoid import error."""
    raise NotImplementedError("cposg_parse_single_json not implemented yet.")


def _extract_header(soup: BeautifulSoup) -> dict:
    """Extract process identifiers and status tags."""
    result = {}
    id_link = soup.select_one("a[href*='processo.codigo']")
    if id_link:
        result['id_original'] = id_link.get_text(strip=True)

    processo_tag = soup.select_one('span.unj-larger')
    if processo_tag:
        result['processo'] = processo_tag.get_text(strip=True)

    status_tags = soup.select('span.unj-tag')
    if status_tags:
        result['status'] = ' / '.join(tag.get_text(strip=True) for tag in status_tags)
    return result


def _extract_labeled_fields(soup: BeautifulSoup) -> dict:
    """Map visible CPOSG labels to canonical result fields."""
    fields = {}
    for div in soup.find_all('div'):
        label_span = div.find('span', class_='unj-label')
        if not label_span:
            continue
        label_text = label_span.get_text(strip=True).lower()
        value_div = div.find('div')
        if not value_div:
            continue
        field_name = next((field for label, field in _FIELD_MAPPING if label in label_text), None)
        if field_name:
            fields[field_name] = value_div.get_text(strip=True)
    return fields


def _extract_movement_text(desc_cell) -> str:
    """Extract a movement label without its italic description."""
    movimento_link = desc_cell.find('a', class_='linkMovVincProc')
    if movimento_link:
        return str(movimento_link.get_text(strip=True))

    temp_cell = BeautifulSoup(str(desc_cell), 'html.parser')
    for span in temp_cell.find_all('span', style=lambda value: value and 'italic' in value):
        span.decompose()

    br_tag = temp_cell.find('br')
    if not br_tag:
        return str(temp_cell.get_text(strip=True))

    movimento = ''.join(
        str(sibling)
        for sibling in br_tag.previous_siblings
        if isinstance(sibling, str)
        or (hasattr(sibling, 'get_text') and getattr(sibling, 'name', None) != 'br')
    ).strip()
    if movimento:
        return movimento
    return str(temp_cell.get_text(separator=' ', strip=True)).split('\n')[0].strip()


def _extract_movements(soup: BeautifulSoup) -> list[dict]:
    """Extract the movement table in displayed order."""
    movs_table = soup.find(id='tabelaTodasMovimentacoes')
    if not movs_table:
        return []

    movements = []
    for row in movs_table.find_all('tr', class_='movimentacaoProcesso'):
        cells = row.find_all('td')
        if len(cells) < 3 or not cells[0].get_text(strip=True):
            continue
        desc_cell = cells[2]
        descricao_span = desc_cell.find('span', style=lambda value: value and 'italic' in value)
        movements.append({
            'data': cells[0].get_text(strip=True),
            'movimento': _extract_movement_text(desc_cell),
            'descricao': descricao_span.get_text(strip=True) if descricao_span else '',
        })
    return movements


def _extract_party_roles(papeis_text: str, *, party_id: int, party_type: str) -> list[dict]:
    """Split the role/name pairs stored in one party cell."""
    roles = []
    for papel in papeis_text.split('\t'):
        papel = papel.strip()
        if not papel:
            continue
        papel_clean = papel.replace('&nbsp', ' ')
        nome_match = re.search(r'(?<=:)\s*([^:]+)$', papel_clean)
        if not nome_match:
            continue
        papel_match = re.search(r'^([^:]+)(?=:)', papel_clean)
        roles.append({
            'id_parte': party_id,
            'nome': nome_match.group(1).strip(),
            'parte': party_type,
            'papel': papel_match.group(1).strip() if papel_match else party_type,
        })
    return roles


def _extract_parties(soup: BeautifulSoup) -> list[dict]:
    """Extract parties and their roles."""
    partes_table = soup.find(id='tableTodasPartes') or soup.find(id='tablePartesPrincipais')
    if not partes_table or soup.find(string=re.compile("Não há Partes")):
        return []

    parties = []
    for index, row in enumerate(partes_table.find_all('tr')):
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        party_type = re.sub(r'[^a-zA-Z]', '', cells[0].get_text(strip=True))
        parties.extend(
            _extract_party_roles(cells[1].get_text(strip=True), party_id=index + 1, party_type=party_type)
        )
    return parties


def _extract_history(soup: BeautifulSoup) -> list[list[str]]:
    """Extract class history rows."""
    hist_table = soup.find(id='tdHistoricoDeClasses')
    if not hist_table:
        return []
    return [
        [cell.get_text(strip=True) for cell in row.find_all('td')]
        for row in hist_table.find_all('tr')
        if row.find_all('td')
    ]


def _extract_decisions(tables: list) -> list[dict]:
    """Extract judgment rows after the judgment-status header."""
    header_index = next(
        (index for index, table in enumerate(tables) if "Situação do julgamento" in table.get_text()),
        -1,
    )
    if header_index < 0 or header_index + 1 >= len(tables):
        return []

    decisions = []
    for table in tables[header_index + 1:]:
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            data = cells[0].get_text(strip=True)
            if data and not data.isalpha():
                decisions.append({
                    'data': data,
                    'situacao': cells[1].get_text(strip=True),
                    'decisao': cells[2].get_text(strip=True),
                })
    return decisions


def _extract_composition(tables: list) -> tuple[list[dict], str | None]:
    """Extract chamber composition and the first relator fallback."""
    composition_table = next(
        (table for table in tables if table.get_text().strip().startswith("Relator")),
        None,
    )
    if composition_table is None:
        return [], None

    composition = []
    fallback_relator = None
    for row in composition_table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        participation = cells[0].get_text(strip=True)
        if not participation:
            continue
        magistrate = cells[1].get_text(strip=True)
        composition.append({'participacao': participation, 'magistrado': magistrate})
        if participation == "Relator" and fallback_relator is None:
            fallback_relator = magistrate
    return composition, fallback_relator


def _extract_first_instance(tables: list) -> list[dict]:
    """Extract first-instance references linked to the appeal."""
    header_index = next(
        (index for index, table in enumerate(tables) if "Nº de 1ª instância" in table.get_text()),
        -1,
    )
    if header_index < 0 or header_index + 1 >= len(tables):
        return []

    first_instance = []
    for row in tables[header_index + 1].find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        first_instance.append({
            'id_1a_inst': cells[0].get_text(strip=True),
            'foro': cells[1].get_text(strip=True),
            'vara': cells[2].get_text(strip=True),
            'juiz': cells[3].get_text(strip=True),
            'obs': cells[4].get_text(strip=True),
        })
    return first_instance


def _fill_html_fallbacks(result: dict, html_content: str) -> None:
    """Fill labeled fields when the page does not expose the expected div structure."""
    if not result.get('classe'):
        classe_match = re.search(r'Classe:\s*([^<]+)', html_content)
        if classe_match:
            result['classe'] = classe_match.group(1).strip()
    if not result.get('assunto'):
        assunto_match = re.search(r'Assunto:\s*([^<]+)', html_content)
        if assunto_match:
            result['assunto'] = assunto_match.group(1).strip()

    for label, field in _FIELD_MAPPING:
        if result.get(field):
            continue
        match = re.search(fr"{label.capitalize()}:\s*([^<\n]+)", html_content, re.IGNORECASE)
        if match:
            result[field] = match.group(1).strip()


def cposg_parse_single_html(html_path):
    """Parse a single HTML document from CPOSG."""
    with Path(html_path).open('r', encoding='utf-8') as file:
        html_content = file.read()
    soup = BeautifulSoup(html_content, 'html.parser')

    if soup.select('.linkProcesso'):
        return []
    if not soup.find(id='tabelaTodasMovimentacoes'):
        return []

    result = _extract_header(soup)
    result.update(_extract_labeled_fields(soup))
    result['movimentacoes'] = _extract_movements(soup)
    result['partes'] = _extract_parties(soup)
    result['historico'] = _extract_history(soup)

    detail_tables = soup.select(f"table[style='{_DETAIL_TABLE_STYLE}']")
    result['decisoes'] = _extract_decisions(detail_tables)
    composition, fallback_relator = _extract_composition(detail_tables)
    if fallback_relator and not result.get('relator'):
        result['relator'] = fallback_relator
    result['composicao'] = composition
    result['primeira_inst'] = _extract_first_instance(detail_tables)

    for field in _REQUIRED_FIELDS:
        result.setdefault(field, None)
    _fill_html_fallbacks(result, html_content)
    return [result]
