"""
Parse of cases from the TJSP jurisprudence search.
"""
import logging
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from bs4.element import Tag
from tqdm import tqdm

from juscraper.courts._esaj.parse import _extract_pagination_count

logger = logging.getLogger("juscraper.cjpg_parse")

_ZERO_RESULT_MARKERS = (
    "nenhum resultado",
    "não foram encontrados",
    "sem resultados",
)


def _has_zero_results(soup: BeautifulSoup) -> bool:
    page_text = soup.get_text().lower()
    return any(marker in page_text for marker in _ZERO_RESULT_MARKERS)


def _find_cjpg_pagination_element(soup: BeautifulSoup) -> Tag | None:
    # A ordem faz parte do contrato legado do CJPG e difere dos seletores
    # compartilhados pelo CJSG. Ver issue #307.
    for cell in soup.find_all("td"):
        if "resultado" in cell.get_text().lower():
            return cell

    legacy_element = soup.find(attrs={"bgcolor": "#EEEEEE"})
    if legacy_element is not None:
        return legacy_element

    for cell in soup.find_all("td"):
        text = cell.get_text().lower()
        if "página" in text and ("de" in text or "total" in text):
            return cell
    return None


def _count_cjpg_result_rows_or_raise(soup: BeautifulSoup) -> int:
    results_container = soup.find("div", {"id": "divDadosResultado"})
    if results_container is not None:
        result_rows = results_container.find_all("tr", class_="fundocinza1")
        if result_rows:
            return len(result_rows)

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
    counts ``tr.fundocinza1`` rows inside ``divDadosResultado`` instead of
    returning a hardcoded ``1`` — ensures ``count_only`` returns a meaningful
    estimate.

    Returns:
        int: Number of results (0 when the search returned no hits).

    Raises:
        ValueError: When no pagination marker is found and the results table
            is also absent — typically signals the search form did not submit
            or the HTML layout changed.
    """
    soup = BeautifulSoup(page_source, "html.parser")

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
    return (n_results + 9) // 10


def cjpg_parse_single(path):
    """
    Parses a downloaded HTML file from the cjpg_download function.
    """
    with Path(path).open('r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    processos = []
    div_dados_resultado = soup.find('div', {'id': 'divDadosResultado'})
    if div_dados_resultado:
        tr_processos = div_dados_resultado.find_all('tr', class_='fundocinza1')
        for tr_processo in tr_processos:
            dados_processo: dict = {}
            tabela_dados = tr_processo.find('table')
            if tabela_dados is None:
                continue
            # id_processo
            link_inteiro_teor = tabela_dados.find('a', {'style': 'vertical-align: top'})
            if link_inteiro_teor:
                name_attr = link_inteiro_teor.get('name')
                if name_attr:
                    dados_processo['cd_processo'] = str(name_attr).split('-')[0]
                else:
                    dados_processo['cd_processo'] = None
                span_negrito = link_inteiro_teor.find('span', class_='fonteNegrito')
                if span_negrito is not None:
                    dados_processo['id_processo'] = span_negrito.text.strip()
                else:
                    dados_processo['id_processo'] = None
            # Outros campos
            linhas_detalhes = tabela_dados.find_all('tr', class_='fonte')
            for linha in linhas_detalhes:
                strong = linha.find('strong')
                if strong:
                    texto = linha.text.strip()
                    chave, valor = texto.split(':', 1)
                    chave = chave.strip().lower().replace(' ', '_').replace('-', '')
                    valor = valor.strip()
                    if chave == 'data_de_disponibilização':
                        chave = 'data_disponibilizacao'
                    dados_processo[chave] = valor
            # Decisão
            div_decisao = tabela_dados.find('div', {'align': 'justify', 'style': 'display: none;'})
            if div_decisao:
                spans = div_decisao.find_all('span')
                decisao_text = spans[-1].get_text(separator=" ", strip=True) if spans else ''
                dados_processo['decisao'] = decisao_text
            processos.append(dados_processo)
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
