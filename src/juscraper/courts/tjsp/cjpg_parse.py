"""
Parse of cases from the TJSP jurisprudence search.
"""
import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

logger = logging.getLogger("juscraper.cjpg_parse")


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

    # Zero-results guard: eSAJ returns the search form (without
    # ``divDadosResultado``) when nothing matches. Mirror the pattern in
    # ``cjsg_n_results`` so ``cjpg_download`` can short-circuit and the public
    # call returns an empty DataFrame instead of raising. Refs #109.
    page_text = soup.get_text().lower()
    if (
        'nenhum resultado' in page_text
        or 'não foram encontrados' in page_text
        or 'sem resultados' in page_text
    ):
        return 0

    # --- Selector cascade ---
    page_element = None

    # 1) <td> containing "Resultados" / "resultados" (current TJSP format,
    #    e.g. "Resultados 1 a 10 de 39764")
    for td in soup.find_all("td"):
        if 'resultado' in td.get_text().lower():
            page_element = td
            break

    # 2) Original selector: bgcolor='#EEEEEE' (legacy format)
    if page_element is None:
        page_element = soup.find(attrs={'bgcolor': '#EEEEEE'})

    # 3) Any <td> that mentions "página" plus "de" or "total"
    if page_element is None:
        for td in soup.find_all("td"):
            txt = td.get_text().lower()
            if 'página' in txt and ('de' in txt or 'total' in txt):
                page_element = td
                break

    # 4) Pagination marker missing but results table present: count rows.
    if page_element is None:
        div_dados = soup.find('div', {'id': 'divDadosResultado'})
        if div_dados is not None and div_dados.find('tr', class_='fundocinza1'):
            n_rows = len(div_dados.find_all('tr', class_='fundocinza1'))
            return max(n_rows, 1)
        raise ValueError(
            "Não foi possível encontrar o seletor de número de páginas "
            "na resposta HTML. Verifique se a busca retornou resultados "
            "ou se a estrutura da página mudou."
        )

    texto = page_element.get_text().strip()

    # --- Regex cascade ---
    # 1) Number at end of text (covers "Resultados 1 a 10 de 39764")
    match = re.search(r'(\d+)\s*$', texto)
    if match is None:
        # 2) Number after "de "
        m2 = re.search(r'(?<=de )([0-9]+)', texto)
        match = m2
    if match is None:
        # 3) Number followed by descriptor
        m3 = re.search(r'([0-9]+)(?=\s*(?:resultado|registro|página))', texto, re.I)
        match = m3
    if match is None:
        # 4) Last resort: pick the largest number found in the text
        nums = re.findall(r'\d+', texto)
        if nums:
            results = max(int(n) for n in nums)
        else:
            raise ValueError(
                "Não foi possível extrair o número de resultados "
                f"da string: {texto}"
            )
    else:
        results = int(match.group(1))

    return results


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
