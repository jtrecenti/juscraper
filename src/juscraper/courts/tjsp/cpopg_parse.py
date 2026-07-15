"""Parses downloaded files from the first-degree procedural query."""
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

# Mapping from normalized dt/dd labels to canonical dados keys
_CANONICAL_KEYS = {
    'assunto': 'assunto',
    'foro': 'foro',
    'vara': 'vara',
    'juiz': 'juiz',
    'classe': 'classe',
    'valor_da_acao': 'valor_acao',
    'distribuicao': 'data_distribuicao',
    'data_de_distribuicao': 'data_distribuicao',
    'recebido_em': 'data_distribuicao',
}

# Regex for CNJ process number format: NNNNNNN-DD.YYYY.J.TR.OOOO
_CNJ_PATTERN = re.compile(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}')

_BASIC_SELECTORS = (
    ('id_processo', 'span', 'numeroProcesso'),
    ('classe', 'span', 'classeProcesso'),
    ('assunto', 'span', 'assuntoProcesso'),
    ('foro', 'span', 'foroProcesso'),
    ('vara', 'span', 'varaProcesso'),
    ('juiz', 'span', 'juizProcesso'),
    ('data_distribuicao', 'div', 'dataHoraDistribuicaoProcesso'),
    ('valor_acao', 'div', 'valorAcaoProcesso'),
)


def _normalize_field_name(label: str) -> str:
    """Convert a Portuguese label like 'Processo principal' to 'processo_principal'."""
    text = label.strip().rstrip(":")
    text = text.lower()
    # remove accents (simple approach for common Portuguese chars)
    replacements = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a',
        'é': 'e', 'ê': 'e',
        'í': 'i',
        'ó': 'o', 'ô': 'o', 'õ': 'o',
        'ú': 'u', 'ü': 'u',
        'ç': 'c',
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return re.sub(r'\s+', '_', text.strip())


def cpopg_parse_manager(path: str):
    """Parse downloaded files from the first-degree procedural query and return a dict of DataFrames.

    Parameters
    ----------
    path : str
        The file path or directory containing the downloaded files.

    Returns
    -------
    dict
        A dictionary where the keys are table names and the values are DataFrames
        with the parsed data from the case files.
    """
    lista_empilhada = {}
    if Path(path).is_file():
        result = [cpopg_parse_single(path)]
    else:
        result = []
        arquivos = [str(f) for f in Path(path).rglob("*.[hj][st]*") if f.is_file()]
        # remover arquivos json cujo nome nao acaba com um número
        arquivos = [f for f in arquivos if not f.endswith('.json') or f[-6:-5].isnumeric()]
        for file in tqdm(arquivos, desc="Processando documentos"):
            if Path(file).is_file():
                try:
                    single_result = cpopg_parse_single(file)
                except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
                    print(f"Erro ao processar o arquivo {file}: {e}")
                    single_result = None
                    continue
                if single_result:
                    result.append(single_result)
        keys = result[0].keys()
        lista_empilhada = {
            key: pd.concat([dic[key] for dic in result], ignore_index=True)
            for key in keys
        }
    # Defensive: if result is empty, return an empty dict or suitable structure
    if not result:
        return lista_empilhada
    return lista_empilhada


def cpopg_parse_single(path: str):
    """Parse a downloaded file from the TJSP CPOPG consultation."""
    # if file extension is html
    if path.endswith('.html'):
        result = cpopg_parse_single_html(path)
    elif path.endswith('.json'):
        result = cpopg_parse_single_json(path)
    else:
        raise ValueError(f"Unknown file extension for path: {path}")
    return result


def _extract_basic_data(soup: BeautifulSoup, path: str) -> dict:
    """Extract stable identifiers from the standard process header."""
    data = {
        'file_path': path,
        'id_processo': None,
        'classe': None,
        'assunto': None,
        'foro': None,
        'vara': None,
        'juiz': None,
        'data_distribuicao': None,
        'valor_acao': None
    }
    for field, tag_name, element_id in _BASIC_SELECTORS:
        tag = soup.find(tag_name, id=element_id)
        if tag:
            data[field] = tag.get_text(strip=True)
    return data


def _fill_incident_header(soup: BeautifulSoup, data: dict) -> None:
    """Fill process number and class from the incident-page header."""
    if data['id_processo'] is not None:
        return

    larger_tag = soup.find('span', class_='unj-larger')
    if not larger_tag:
        return

    text = larger_tag.get_text(strip=True)
    match = _CNJ_PATTERN.search(text)
    if match:
        data['id_processo'] = match.group(0)
    if data['classe'] is None:
        classe_text = re.sub(r'\s*\(.*$', '', text).replace('\xa0', ' ').strip()
        if classe_text:
            data['classe'] = classe_text


def _extract_labeled_value(label_span) -> tuple[str, str] | None:
    """Resolve one dynamic label and its sibling value."""
    key = _normalize_field_name(label_span.get_text(strip=True))
    if not key:
        return None
    parent_col = label_span.find_parent('div', class_=re.compile(r'^col-'))
    if parent_col is None:
        return None
    value_div = parent_col.find('div')
    if value_div is None or value_div.find('span', class_='unj-larger'):
        return None
    value = value_div.get_text(strip=True)
    if not value:
        return None
    return _CANONICAL_KEYS.get(key, key), value


def _fill_extra_fields(soup: BeautifulSoup, data: dict) -> None:
    """Fill dynamic fields represented by visible unj-label spans."""
    sections = (
        section
        for section in (soup.find('div', id='containerDadosPrincipaisProcesso'), soup.find('div', id='maisDetalhes'))
        if section is not None
    )
    for section in sections:
        for label_span in section.find_all('span', class_='unj-label'):
            extracted = _extract_labeled_value(label_span)
            if extracted is None:
                continue
            canonical, value = extracted
            if canonical not in data or data[canonical] is None:
                data[canonical] = value


def _extract_party_row(row, path: str) -> dict | None:
    """Convert one first-degree party row to the public table shape."""
    cells = row.find_all('td')
    if len(cells) < 2:
        return None

    type_tag = cells[0].find('span', class_='tipoDeParticipacao')
    party_type = type_tag.get_text(strip=True) if type_tag else ''
    raw_text = cells[1].get_text('||', strip=True)
    lawyers = []
    if 'Advogado:' in raw_text:
        split_text = raw_text.split('Advogado:')
        party_name = split_text[0].replace('||', ' ').strip()
        lawyers.append(split_text[1].replace('||', ' ').strip())
    else:
        party_name = raw_text.replace('||', ' ').strip()

    if not party_name:
        return None
    return {
        'file_path': path,
        'tipo': party_type,
        'nome': party_name,
        'advogados': lawyers,
    }


def _extract_parties(soup: BeautifulSoup, path: str) -> list[dict]:
    """Extract parties and lawyers in source order."""
    table = soup.find('table', id='tablePartesPrincipais')
    if not table:
        return []
    return [
        party
        for row in table.find_all('tr')
        if (party := _extract_party_row(row, path)) is not None
    ]


def _extract_movement_row(row, path: str) -> dict | None:
    """Convert one movement row to the public table shape."""
    cells = row.find_all('td')
    if len(cells) < 3:
        return None

    description_cell = cells[2]
    main_description = description_cell.find(string=True, recursive=False) or ''
    italic_span = description_cell.find('span', style='font-style: italic;')
    return {
        'file_path': path,
        'data': cells[0].get_text(strip=True),
        'movimento': main_description.strip(),
        'observacao': italic_span.get_text(strip=True) if italic_span else '',
    }


def _extract_movements(soup: BeautifulSoup, path: str) -> list[dict]:
    """Extract all visible process movements."""
    table = soup.find('tbody', id='tabelaTodasMovimentacoes')
    if not table:
        return []
    return [
        movement
        for row in table.find_all('tr', class_='containerMovimentacao')
        if (movement := _extract_movement_row(row, path)) is not None
    ]


def _extract_petition_row(row, path: str) -> dict | None:
    """Convert one miscellaneous-petition row to the public table shape."""
    cells = row.find_all('td')
    if len(cells) != 2:
        return None
    return {
        'file_path': path,
        'data': cells[0].get_text(strip=True),
        'tipo': cells[1].get_text(strip=True),
    }


def _extract_misc_petitions(soup: BeautifulSoup, path: str) -> list[dict]:
    """Extract the table following the miscellaneous-petitions heading."""
    heading = soup.find(lambda tag: tag.name == 'h2' and tag.get_text(strip=True) == 'Petições diversas')
    if not heading:
        return []
    table = heading.find_next('table')
    if not table:
        return []
    return [
        petition
        for row in table.find_all('tr')
        if (petition := _extract_petition_row(row, path)) is not None
    ]


def cpopg_parse_single_html(path: str):
    """Parse a downloaded HTML file from the TJSP CPOPG consultation."""
    with Path(path).open('r', encoding='utf-8') as file:
        soup = BeautifulSoup(file.read(), 'html.parser')

    basic_data = _extract_basic_data(soup, path)
    _fill_incident_header(soup, basic_data)
    _fill_extra_fields(soup, basic_data)

    return {
        'basicos': pd.DataFrame([basic_data]),
        'partes': pd.DataFrame(_extract_parties(soup, path)),
        'movimentacoes': pd.DataFrame(_extract_movements(soup, path)),
        'peticoes_diversas': pd.DataFrame(_extract_misc_petitions(soup, path)),
    }


def cpopg_parse_single_json(path: str):
    """Parse a JSON file downloaded by cpopg_download."""
    # primeiro, vamos listar todos os arquivos que estão na
    # mesma pasta que o arquivo que está em path
    lista_arquivos = [str(p) for p in Path(path).parent.glob("*.json")]
    lista_processo = next(f for f in lista_arquivos if f[-6:-5].isnumeric())
    lista_arquivos = [f for f in lista_arquivos if f not in lista_processo]

    # agora, fazemos a leitura de cada arquivo e transformamos em um dataframe
    dfs = {}
    for arquivo in lista_arquivos:
        nome = Path(arquivo).name
        # split name in two variables separating by _
        cd_processo, tipo = nome.split("_", 1)
        tipo = tipo.split(".", 1)[0]
        if 'basicos' in arquivo:
            df = pd.read_json(arquivo, orient='index').transpose()
        else:
            df = pd.read_json(arquivo, orient='records')
        df['cdProcesso'] = cd_processo
        if tipo not in dfs:
            dfs[tipo] = df
        else:
            dfs[tipo] = pd.concat([dfs[tipo], df], ignore_index=True)
    df_processo = pd.read_json(lista_processo, orient='records')
    df_processo = df_processo.merge(dfs['basicos'], how='left', on='cdProcesso')
    dfs['basicos'] = df_processo
    return dfs


def get_cpopg_download_links(request):
    """Return the download links for the listed processes."""
    text = request.text
    bsoup = BeautifulSoup(text, 'html.parser')
    lista = bsoup.find('div', {'id': 'listagemDeProcessos'})
    links: list = []
    if lista is None:
        id_tag = bsoup.find('form', {'id': 'popupSenha'})
        if id_tag is None:
            return links
        href = id_tag.get('action')
        if href is not None and 'show.do' in str(href):
            links.append(href)
    else:
        links.extend(str(a['href']) for a in lista.find_all('a', href=True))
    return links
