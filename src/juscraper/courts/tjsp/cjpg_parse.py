"""
Parse of cases from the TJSP jurisprudence search.
"""
import logging
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from bs4.element import Tag
from tqdm import tqdm

from juscraper.courts._esaj.parse import (
    _extract_pagination_count,
    _find_page_summary_cell,
    _has_zero_results,
    _raise_page_error,
)

logger = logging.getLogger("juscraper.cjpg_parse")

_CJPG_PAGE_SIZE = 10


def _find_cjpg_pagination_element(soup: BeautifulSoup) -> Tag | None:
    # A cascata do CJPG difere da que o CJSG usa em
    # ``_esaj.parse._find_pagination_element``. Aqui qualquer ``td`` com
    # "resultado" vence, sem o limite de 400 caracteres, antes de ``bgcolor``,
    # e ``bgcolor`` vale em qualquer tag. O CJSG exige "resultados" em célula
    # curta e ainda tenta ``td`` com classe "pag". A ordem faz parte do
    # contrato legado do CJPG: unificar as duas mudaria qual célula é lida
    # em páginas que casam com mais de um seletor.
    for cell in soup.find_all("td"):
        if "resultado" in cell.get_text().lower():
            return cell

    legacy_element = soup.find(attrs={"bgcolor": "#EEEEEE"})
    if legacy_element is not None:
        return legacy_element

    return _find_page_summary_cell(soup)


def _count_cjpg_result_rows_or_raise(soup: BeautifulSoup) -> int:
    results_container = soup.find("div", {"id": "divDadosResultado"})
    if results_container is not None:
        result_rows = results_container.find_all("tr", class_="fundocinza1")
        if 0 < len(result_rows) < _CJPG_PAGE_SIZE:
            return len(result_rows)
        if len(result_rows) >= _CJPG_PAGE_SIZE:
            raise ValueError(
                "A resposta contém uma página completa de resultados sem "
                "marcador de paginação; o HTML pode estar truncado."
            )

    raise ValueError(
        "Não foi possível encontrar o seletor de número de páginas "
        "na resposta HTML. Verifique se a busca retornou resultados "
        "ou se a estrutura da página mudou."
    )


def cjpg_n_results(page_source) -> int:
    """Extracts the total number of results from a CJPG first-page HTML.

    Sibling of :func:`cjpg_n_pags`, which is now a thin wrapper that divides
    by the 10-hits-per-page constant. Used by the ``count_only=True``
    short-circuit in :meth:`TJSPScraper.cjpg` (issue #92).

    Uses cascading selector + regex strategy to tolerate TJSP layout changes.
    Mirrors :func:`juscraper.courts._esaj.parse.cjsg_n_results`.

    Fallback for "results table present but pagination marker missing":
    counts ``tr.fundocinza1`` rows inside ``divDadosResultado`` when the page
    has fewer than 10 rows. A full page without pagination is ambiguous and
    raises instead of undercounting a potentially truncated response.

    Returns:
        int: Number of results (0 when the search returned no hits).

    Raises:
        ValueError: When the page reports an error, contains a full results
            page without pagination, or has no known result marker.
    """
    soup = BeautifulSoup(page_source, "html.parser")

    _raise_page_error(soup)
    if _has_zero_results(soup):
        return 0

    page_element = _find_cjpg_pagination_element(soup)
    if page_element is None:
        return _count_cjpg_result_rows_or_raise(soup)

    pagination_text = page_element.get_text().strip()
    count = _extract_pagination_count(pagination_text)
    if count is None:
        raise ValueError(
            "Não foi possível extrair o número de resultados "
            f"da string: {pagination_text}"
        )
    return count


def cjpg_n_pags(page_source) -> int:
    """Extracts the number of pages from a CJPG first-page HTML.

    Thin wrapper over :func:`cjpg_n_results` that converts result count into
    page count via ``ceil(n_results / 10)`` (CJPG serves 10 hits per page;
    differs from CJSG's 20).
    """
    n_results = cjpg_n_results(page_source)
    if n_results == 0:
        return 0
    return (n_results + _CJPG_PAGE_SIZE - 1) // _CJPG_PAGE_SIZE


def _extrair_dados_processo(tabela_dados):
    """Extrai identificadores, detalhes e decisão de uma tabela CJPG."""
    dados_processo: dict = {}
    link_inteiro_teor = tabela_dados.find('a', {'style': 'vertical-align: top'})
    if link_inteiro_teor:
        nome = link_inteiro_teor.get('name')
        dados_processo['cd_processo'] = str(nome).split('-')[0] if nome else None
        span_negrito = link_inteiro_teor.find('span', class_='fonteNegrito')
        dados_processo['id_processo'] = span_negrito.text.strip() if span_negrito is not None else None

    for linha in tabela_dados.find_all('tr', class_='fonte'):
        if linha.find('strong'):
            chave, valor = linha.text.strip().split(':', 1)
            chave = chave.strip().lower().replace(' ', '_').replace('-', '')
            if chave == 'data_de_disponibilização':
                chave = 'data_disponibilizacao'
            dados_processo[chave] = valor.strip()

    div_decisao = tabela_dados.find('div', {'align': 'justify', 'style': 'display: none;'})
    if div_decisao:
        spans = div_decisao.find_all('span')
        dados_processo['decisao'] = spans[-1].get_text(separator=" ", strip=True) if spans else ''
    return dados_processo


def cjpg_parse_single(path):
    """
    Parses a downloaded HTML file from the cjpg_download function.
    """
    with Path(path).open('r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    processos = []
    div_dados_resultado = soup.find('div', {'id': 'divDadosResultado'})
    if div_dados_resultado:
        for tr_processo in div_dados_resultado.find_all('tr', class_='fundocinza1'):
            tabela_dados = tr_processo.find('table')
            if tabela_dados is not None:
                processos.append(_extrair_dados_processo(tabela_dados))
    return pd.DataFrame(processos)


def cjpg_parse_manager(path):
    """
    Parses the downloaded files from the cjpg_download function.
    Returns a DataFrame with the information of the processes.
    """
    if Path(path).is_file():
        result = [cjpg_parse_single(path)]
    else:
        result = []
        arquivos = [f for f in Path(path).rglob("*.ht*") if f.is_file()]
        for file in tqdm(arquivos, desc="Processando documentos"):
            if file.is_file():
                try:
                    single_result = cjpg_parse_single(file)
                except (ValueError, OSError) as e:
                    logger.error('Error processing %s: %s', file, e)
                    single_result = None
                    continue
                if single_result is not None:
                    result.append(single_result)
    return pd.concat(result, ignore_index=True)
