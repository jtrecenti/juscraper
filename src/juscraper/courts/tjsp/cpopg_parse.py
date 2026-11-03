"""Parses downloaded files from the first-degree procedural query."""
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString
from tqdm import tqdm

from ...core.avisos import avisar

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
_BASIC_COLUMNS = ('file_path', *(field for field, _, _ in _BASIC_SELECTORS), 'situacao')
_PARTY_COLUMNS = ('file_path', 'tipo', 'nome', 'advogados')
_MOVEMENT_COLUMNS = ('file_path', 'data', 'movimento', 'observacao')
_MISC_PETITION_COLUMNS = ('file_path', 'data', 'tipo')
# Label written as bare text, without the span the eSAJ uses (legacy samples).
_BARE_LAWYER_LABEL = re.compile(r'Advogad[oa]:')


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
        with the parsed data from the case files. When ``path`` is a directory,
        files that fail to parse are reported with ``print`` and skipped.

    Raises
    ------
    ValueError
        When ``path`` is a directory and no file in it could be parsed, either
        because it holds no candidate ``.html``/``.json`` file or because every
        candidate failed. Returning ``{}`` here would hide a download or read
        failure behind an empty result.
    """
    root = Path(path)
    if root.is_file():
        return cpopg_parse_single(str(root))

    files = [
        file
        for file in root.rglob("*.[hj][st]*")
        if file.is_file() and (file.suffix != '.json' or file.name[-6:-5].isnumeric())
    ]
    parsed = []
    falhas = 0
    for file in tqdm(files, desc="Processando documentos"):
        try:
            single_result = cpopg_parse_single(str(file))
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as error:
            print(f"Erro ao processar o arquivo {file}: {error}")
            falhas += 1
            continue
        if single_result:
            parsed.append(single_result)

    if not parsed:
        raise _nothing_parsed_error(root, len(files), falhas)
    return {
        key: pd.concat([result[key] for result in parsed], ignore_index=True)
        for key in parsed[0]
    }


def _nothing_parsed_error(root: Path, candidatos: int, falhas: int) -> ValueError:
    """Build the error for a directory where no CPOPG file could be parsed."""
    if candidatos == 0:
        return ValueError(
            f"Nenhum arquivo do CPOPG lido em {root}: nenhum arquivo candidato "
            "(.html ou .json de processo) encontrado no diretório."
        )
    return ValueError(
        f"Nenhum arquivo do CPOPG lido em {root}: {candidatos} arquivo(s) candidato(s), "
        f"{falhas} com erro. Os erros de cada arquivo foram impressos acima."
    )


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
    data = dict.fromkeys(_BASIC_COLUMNS)
    data['file_path'] = path
    for field, tag_name, element_id in _BASIC_SELECTORS:
        tag = soup.find(tag_name, id=element_id)
        if tag:
            data[field] = tag.get_text(strip=True)
    data['situacao'] = _extract_status(soup)
    return data


def _extract_status(soup: BeautifulSoup) -> str | None:
    """Return the status tag of the process header ("Extinto", "Suspenso"...).

    The main-process header marks it as ``#labelSituacaoProcesso``; the
    incident header puts an unnamed ``unj-tag`` in the same ``div`` as the
    ``unj-larger`` class and number. Other tags of the header, such as
    "Tramitação prioritária", sit outside both places.
    """
    tag = soup.find('span', id='labelSituacaoProcesso')
    if tag is None:
        header = soup.find('div', id='containerDadosPrincipaisProcesso')
        larger_tag = header.find('span', class_='unj-larger') if header else None
        tag = larger_tag.parent.find('span', class_='unj-tag') if larger_tag else None
    return tag.get_text(strip=True) if tag else None


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


def _split_party_cell(cell: Tag) -> tuple[str, list[str]]:
    """Split a party cell into the party name and its representatives.

    Each representative comes after a ``span.mensagemExibindo`` label, whose
    text varies with the role and gender ("Advogado:", "Advogada:", "Soc.
    Advogados:", "Def. Púb:", "Procurador:"); the split follows the span, not
    the text. A bare "Advogado:"/"Advogada:" text node also splits, for
    pages without the span. Comments are skipped, as ``get_text`` does.
    """
    groups: list[list[str]] = [[]]
    for node in cell.descendants:
        # PreformattedString covers comments, CDATA and doctypes.
        if not isinstance(node, NavigableString) or isinstance(node, PreformattedString):
            continue
        parent = node.parent
        is_label_span = parent is not None and parent.name == 'span' and 'mensagemExibindo' in parent.get('class', [])
        if is_label_span or _BARE_LAWYER_LABEL.fullmatch(node.strip()):
            groups.append([])
        elif node.strip():
            groups[-1].append(node.strip())
    party_name, *lawyers = (' '.join(group) for group in groups)
    return party_name, [lawyer for lawyer in lawyers if lawyer]


def _extract_parties(soup: BeautifulSoup, path: str) -> list[dict]:
    """Extract parties and lawyers in source order."""
    table = soup.find('table', id='tablePartesPrincipais')
    if not table:
        return []
    parties = []
    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        type_tag = cells[0].find('span', class_='tipoDeParticipacao')
        party_type = type_tag.get_text(strip=True) if type_tag else ''
        party_name, lawyers = _split_party_cell(cells[1])
        if not party_name:
            continue
        parties.append({
            'file_path': path,
            'tipo': party_type,
            'nome': party_name,
            'advogados': lawyers,
        })
    return parties


def _movement_rows(soup: BeautifulSoup, path: str) -> list[Tag]:
    """Return the movement rows of the page, in the order the eSAJ lists them.

    Older pages carry the whole list in ``#tabelaTodasMovimentacoes``. Current
    pages leave ``#containerMovimentacoes`` empty until "Exibir movimentações";
    ``cpopg_download`` fills it with every page of the list. A page that still
    has the button was saved without the list, and an empty table there would
    read as a process without movements.
    """
    table = soup.find('tbody', id='tabelaTodasMovimentacoes')
    if table is not None:
        return list(table.find_all('tr', class_='containerMovimentacao'))
    if soup.find(id='btnExibirMovimentacoes') is not None:
        avisar(
            f"{path}: a página do processo não traz as movimentações, que o eSAJ "
            "carrega à parte; a tabela 'movimentacoes' sai vazia para ele. "
            "Baixe o processo de novo com cpopg_download, que substitui o HTML "
            "salvo sem as movimentações."
        )
        return []
    container = soup.find('div', id='containerMovimentacoes')
    if container is None:
        return []
    return list(container.find_all('tr', class_='containerMovimentacao'))


def _movement_description(cell: Tag) -> str:
    """Movement name; rows with a linked document carry it inside the link."""
    link = cell.find('a', class_='linkMovVincProc')
    if link is not None:
        return str(link.get_text(' ', strip=True))
    return ' '.join(text.strip() for text in cell.find_all(string=True, recursive=False) if text.strip())


def _extract_movements(soup: BeautifulSoup, path: str) -> list[dict]:
    """Extract all process movements."""
    movements = []
    for row in _movement_rows(soup, path):
        cells = row.find_all('td')
        if len(cells) < 3:
            continue
        description_cell = cells[2]
        italic_span = description_cell.find('span', style='font-style: italic;')
        movements.append({
            'file_path': path,
            'data': cells[0].get_text(strip=True),
            'movimento': _movement_description(description_cell),
            'observacao': italic_span.get_text(strip=True) if italic_span else '',
        })
    return movements


def _extract_misc_petitions(soup: BeautifulSoup, path: str) -> list[dict]:
    """Extract the table following the miscellaneous-petitions heading."""
    heading = soup.find(lambda tag: tag.name == 'h2' and tag.get_text(strip=True) == 'Petições diversas')
    if not heading:
        return []
    table = heading.find_next('table')
    if not table:
        return []
    petitions = []
    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) == 2:
            petitions.append({
                'file_path': path,
                'data': cells[0].get_text(strip=True),
                'tipo': cells[1].get_text(strip=True),
            })
    return petitions


def cpopg_parse_single_html(path: str):
    """Parse a downloaded HTML file from the TJSP CPOPG consultation."""
    with Path(path).open('r', encoding='utf-8') as file:
        soup = BeautifulSoup(file.read(), 'html.parser')

    basic_data = _extract_basic_data(soup, path)
    _fill_incident_header(soup, basic_data)
    _fill_extra_fields(soup, basic_data)

    return {
        'basicos': pd.DataFrame([basic_data]),
        'partes': pd.DataFrame(_extract_parties(soup, path), columns=_PARTY_COLUMNS),
        'movimentacoes': pd.DataFrame(_extract_movements(soup, path), columns=_MOVEMENT_COLUMNS),
        'peticoes_diversas': pd.DataFrame(_extract_misc_petitions(soup, path), columns=_MISC_PETITION_COLUMNS),
    }


def cpopg_parse_single_json(path: str):
    """Parse a JSON file downloaded by cpopg_download."""
    # primeiro, vamos listar todos os arquivos que estão na
    # mesma pasta que o arquivo que está em path
    lista_arquivos = [str(p) for p in Path(path).parent.glob("*.json")]
    lista_processo = next(f for f in lista_arquivos if f[-6:-5].isnumeric())
    lista_arquivos = [f for f in lista_arquivos if f not in lista_processo]
    df_processo = pd.read_json(lista_processo, orient='records')
    if df_processo.empty:
        # A busca por número devolve [] sem baixar os demais JSONs; sem esta
        # checagem, o merge abaixo levantava KeyError: 'basicos'.
        raise ValueError(
            f"A API do TJSP não devolveu nenhum processo para {Path(lista_processo).stem} "
            "(resposta []). O processo pode existir mesmo assim: consulte com method='html'."
        )

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
    # Com baixar_movimentacoes=False não há arquivo de movimentação; a chave fica,
    # porque cpopg_parse_manager junta as tabelas pelas chaves do primeiro processo.
    dfs.setdefault('movimentacao', pd.DataFrame(columns=['cdProcesso']))
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
