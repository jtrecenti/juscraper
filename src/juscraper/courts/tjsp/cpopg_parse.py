"""Parses downloaded files from the first-degree procedural query."""
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString
from tqdm import tqdm

from ...core.avisos import avisar
from ...core.failures import COLUNA_MOTIVO_FALHA, MOTIVO_RESPOSTA_INESPERADA
from .._esaj.pasta import documento_vinculado
from ._falhas import avisar_falhas_de_processo, cnj_da_pasta, com_linhas_de_falha, processos_sem_arquivo
from .cpopg_download import caminho_do_documento, listagem_de_processos

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
_MOVEMENT_COLUMNS = (
    'file_path', 'data', 'movimento', 'observacao', 'cd_documento', 'documento_publico', 'caminho_documento',
)
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


def cpopg_parse_manager(path: str, metodo: str = "TJSPScraper.cpopg_parse"):
    """Parse downloaded files from the first-degree procedural query and return a dict of DataFrames.

    Parameters
    ----------
    path : str
        The file path or directory containing the downloaded files.
    metodo : str
        Método público que abre o ``UserWarning`` das falhas.

    Returns
    -------
    dict
        A dictionary where the keys are table names and the values are DataFrames
        with the parsed data from the case files. Quando ``path`` é um
        diretório, ``basicos`` ganha a coluna ``motivo_falha``: ``None`` em
        cada arquivo lido e ``resposta_inesperada`` no arquivo que o parser
        recusa, que fica numa linha com ``file_path``, ``id_processo`` (o CNJ
        da pasta do processo) e as demais colunas ``None``. O processo que
        ``cpopg_download`` não baixou nessa pasta ganha uma linha com
        ``id_processo`` e o motivo do download. As falhas também saem num
        único ``UserWarning``.

    Raises
    ------
    ValueError
        Quando ``path`` é um diretório e nenhum arquivo dele pôde ser lido,
        porque todos falharam ou porque não há ``.html`` nem falha de
        download registrada. Devolver ``{}`` esconderia uma falha de download
        ou de leitura atrás de um resultado vazio.
    """
    root = Path(path)
    if root.is_file():
        return cpopg_parse_single(str(root))

    files = arquivos_candidatos(root)
    sem_arquivo = processos_sem_arquivo(root / 'cpopg' if (root / 'cpopg').is_dir() else root, files)
    parsed, falhas = _ler_arquivos(files)
    if parsed:
        result = {
            key: pd.concat([result[key] for result in parsed], ignore_index=True)
            for key in parsed[0]
        }
    elif sem_arquivo and not files:
        # Lote em que nenhum processo foi baixado: as linhas de falha vão em tabelas vazias.
        result = tabelas_vazias()
    else:
        raise _nothing_parsed_error(root, len(files), falhas)
    result['basicos'] = com_linhas_de_falha(result['basicos'], [
        *({'file_path': str(file), 'id_processo': cnj_da_pasta(file), COLUNA_MOTIVO_FALHA: MOTIVO_RESPOSTA_INESPERADA}
          for file, _ in falhas),
        *({'id_processo': cnj, COLUNA_MOTIVO_FALHA: motivo} for cnj, motivo in sem_arquivo.items()),
    ])
    avisar_falhas_de_processo(
        sem_arquivo,
        [f"{file}: {MOTIVO_RESPOSTA_INESPERADA} ({error})" for file, error in falhas],
        metodo,
        "Eles saem na tabela basicos",
    )
    return result


def _ler_arquivos(files: list[Path]) -> tuple[list[dict], list[tuple[Path, Exception]]]:
    """As tabelas de cada arquivo lido e o erro de cada arquivo que o parser recusou."""
    parsed = []
    falhas: list[tuple[Path, Exception]] = []
    for file in tqdm(files, desc="Processando documentos"):
        try:
            single_result = cpopg_parse_single(str(file))
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as error:
            falhas.append((file, error))
            continue
        if single_result:
            parsed.append(single_result)
    return parsed, falhas


def arquivos_candidatos(root: Path) -> list[Path]:
    """Os ``.html`` de processo sob ``root``, que :func:`cpopg_parse_manager` lê."""
    return [file for file in root.rglob("*.html") if file.is_file()]


def tabelas_vazias() -> dict[str, pd.DataFrame]:
    """As quatro tabelas do ``cpopg`` sem linhas, para o lote em que nenhum processo foi baixado."""
    return {
        'basicos': pd.DataFrame(columns=[*_BASIC_COLUMNS, COLUNA_MOTIVO_FALHA]),
        'partes': pd.DataFrame(columns=list(_PARTY_COLUMNS)),
        'movimentacoes': pd.DataFrame(columns=list(_MOVEMENT_COLUMNS)),
        'peticoes_diversas': pd.DataFrame(columns=list(_MISC_PETITION_COLUMNS)),
    }


def _nothing_parsed_error(root: Path, candidatos: int, falhas: list[tuple[Path, Exception]]) -> ValueError:
    """Build the error for a directory where no CPOPG file could be parsed."""
    if candidatos == 0:
        return ValueError(
            f"Nenhum arquivo do CPOPG lido em {root}: nenhum arquivo candidato "
            "(.html de processo) encontrado no diretório."
        )
    arquivo, erro = falhas[0]
    return ValueError(
        f"Nenhum arquivo do CPOPG lido em {root}: {candidatos} arquivo(s) candidato(s), "
        f"{len(falhas)} com erro. Primeiro erro, em {arquivo.name}: {erro}"
    )


def cpopg_parse_single(path: str):
    """Parse a downloaded file from the TJSP CPOPG consultation."""
    if not path.endswith('.html'):
        raise ValueError(f"Unknown file extension for path: {path}")
    return cpopg_parse_single_html(path)


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

    cnj, classe = _split_incident_header(larger_tag.get_text(strip=True))
    if cnj:
        data['id_processo'] = cnj
    if data['classe'] is None and classe:
        data['classe'] = classe


def _split_incident_header(text: str) -> tuple[str | None, str | None]:
    """Separa o cabeçalho de incidente do eSAJ, "Classe (CNJ)", em ``(cnj, classe)``.

    Usado pelos parsers do cpopg e do cposg; a parte ausente vem ``None``. A
    classe é o texto antes do CNJ, então um número sozinho não gera classe.
    """
    match = _CNJ_PATTERN.search(text)
    head = text[:match.start()] if match else text
    classe = re.sub(r'\s*\(.*$', '', head).replace('\xa0', ' ').strip()
    return (match.group(0) if match else None), (classe or None)


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


def _movement_document(row: Tag, path: str) -> dict:
    """Document linked to the movement: code, whether it opens without password, and the PDF if downloaded.

    Rows without a document get ``None`` in the three columns. The PDF is the
    one ``cpopg_download(..., download_pecas=True)`` saves next to the HTML.
    """
    link = row.find('a', class_='linkMovVincProc')
    documento = documento_vinculado(link) if isinstance(link, Tag) else None
    if documento is None:
        return dict.fromkeys(('cd_documento', 'documento_publico', 'caminho_documento'))
    pdf = caminho_do_documento(Path(path).parent, documento.cd_documento)
    return {
        'cd_documento': documento.cd_documento,
        'documento_publico': documento.publico,
        'caminho_documento': str(pdf) if pdf.is_file() else None,
    }


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
            **_movement_document(row, path),
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


def get_cpopg_download_links(request):
    """Return the download links for the listed processes."""
    text = request.text
    bsoup = BeautifulSoup(text, 'html.parser')
    lista = listagem_de_processos(bsoup)
    links: list = []
    if lista is None:
        id_tag = bsoup.find('form', {'id': 'popupSenha'})
        if id_tag is None:
            return links
        href = id_tag.get('action')
        if href is not None and 'show.do' in str(href):
            links.append(href)
    else:
        # A listagem também traz âncoras de interface, como o colapso
        # "Incidentes e recursos" (href="#"); só os links para show.do
        # são processos.
        links.extend(
            str(a['href']) for a in lista.find_all('a', href=True)
            if 'show.do' in str(a['href'])
        )
    return links
