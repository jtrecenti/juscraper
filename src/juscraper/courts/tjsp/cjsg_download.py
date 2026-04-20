"""Download results from the TJSP Consulta de Julgados de Segundo Grau (CJSG).

Uses requests library only (no browser automation needed).
"""
import logging
import os
import time
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from juscraper.utils.params import to_br_date

logger = logging.getLogger("juscraper.cjsg_download")


# Limite imposto pelo backend do eSAJ no campo "buscaInteiroTeor" do CJSG.
# Strings maiores são truncadas silenciosamente pelo TJSP, levando a
# resultados inesperados — preferimos abortar na origem.
_TJSP_PESQUISA_MAX_CHARS = 120


class QueryTooLongError(ValueError):
    """Raised when the search query exceeds the TJSP backend maximum length."""


def cjsg_download(
    pesquisa: str,
    download_path: str,
    u_base: str,
    sleep_time: float = 0.5,
    verbose: int = 1,
    ementa: Optional['str | None'] = None,
    classe: Optional['str | None'] = None,
    assunto: Optional['str | None'] = None,
    comarca: Optional['str | None'] = None,
    orgao_julgador: Optional['str | None'] = None,
    data_inicio: Optional['str | None'] = None,
    data_fim: Optional['str | None'] = None,
    baixar_sg: bool = True,
    tipo_decisao: str = 'acordao',
    paginas: Optional['list | range | None'] = None,
    get_n_pags_callback=None,
):
    """Download HTML files from the CJSG search results pages.

    Uses requests library only, following the same approach as the R implementation.
    No browser automation is needed.

    Args:
        pesquisa (str): Search term. Maximum 120 characters (TJSP backend limit).
        download_path (str): Base directory for saving files.
        u_base (str): ESAJ base URL.
        sleep_time (float): Time to wait between requests.
        verbose (int): Logging level.
        ementa, classe, assunto, comarca, orgao_julgador, data_inicio, data_fim: Optional filters.
        baixar_sg (bool): If True, downloads from second stage (sg="T"), otherwise from recursal (cr="R").
        tipo_decisao (str): 'acordao' or 'monocratica'.
        paginas (range): Page range to download (1-based, e.g., range(1, 4) downloads pages 1-3).
        get_n_pags_callback (callable): Callback function to extract number of pages from HTML.
    """
    if pesquisa is not None and len(pesquisa) > _TJSP_PESQUISA_MAX_CHARS:
        raise QueryTooLongError(
            f"O campo 'pesquisa' do CJSG do TJSP aceita no máximo "
            f"{_TJSP_PESQUISA_MAX_CHARS} caracteres "
            f"(recebido: {len(pesquisa)} caracteres). "
            "Reduza a busca ou divida em consultas menores."
        )
    if get_n_pags_callback is None:
        raise ValueError(
            'É necessário fornecer get_n_pags_callback para extrair o número de páginas.'
        )

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = f"{download_path}/cjsg/{timestamp}"
    if not os.path.isdir(path):
        os.makedirs(path)

    # Create a session to maintain cookies
    session = requests.Session()

    # Set headers to match browser request
    session.headers.update({
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        ),
    })

    # Build the POST body for the search form
    # Following the structure from the R code
    body = {
        'dados.buscaInteiroTeor': pesquisa,
        'dados.pesquisarComSinonimos': 'S',
        'dados.buscaEmenta': ementa or '',
        'dados.nuProcOrigem': '',
        'dados.nuRegistro': '',
        'agenteSelectedEntitiesList': '',
        'contadoragente': '0',
        'contadorMaioragente': '0',
        'codigoCr': '',
        'codigoTr': '',
        'nmAgente': '',
        'juizProlatorSelectedEntitiesList': '',
        'contadorjuizProlator': '0',
        'contadorMaiorjuizProlator': '0',
        'codigoJuizCr': '',
        'codigoJuizTr': '',
        'nmJuiz': '',
        'classesTreeSelection.values': classe or '',
        'classesTreeSelection.text': '',
        'assuntosTreeSelection.values': assunto or '',
        'assuntosTreeSelection.text': '',
        'comarcaSelectedEntitiesList': '',
        'contadorcomarca': '1',
        'contadorMaiorcomarca': '1',
        'cdComarca': comarca or '',
        'nmComarca': '',
        'secoesTreeSelection.values': orgao_julgador or '',
        'secoesTreeSelection.text': '',
        'dados.dtJulgamentoInicio': to_br_date(data_inicio) or '',
        'dados.dtJulgamentoFim': to_br_date(data_fim) or '',
        'dados.dtRegistroInicio': '',
        'dados.dtRegistroFim': '',
        'dados.ordenacao': 'dtPublicacao',
    }

    # Set origem based on baixar_sg parameter
    # sg="T" for second stage, cr="R" for recursal
    if baixar_sg:
        body['dados.origensSelecionadas'] = 'T'
    else:
        body['dados.origensSelecionadas'] = 'R'

    # Set tipo de decisão: "A" for acordao, "D" for monocratica
    body['tipoDecisaoSelecionados'] = 'A' if tipo_decisao == 'acordao' else 'D'

    # POST to resultadoCompleta.do
    link_cjsg = f"{u_base}cjsg/resultadoCompleta.do"

    try:
        if verbose > 0:
            logger.info("Submetendo formulário de busca...")

        response = session.post(
            link_cjsg,
            data=body,
            timeout=30,
            allow_redirects=True
        )
        response.raise_for_status()

        # Get the first page using trocaDePagina.do
        # This is what the R code does: GET trocaDePagina.do?tipoDeDecisao=A&pagina=1
        tipo_decisao_param = 'A' if tipo_decisao == 'acordao' else 'D'
        first_page_url = f"{u_base}cjsg/trocaDePagina.do?tipoDeDecisao={tipo_decisao_param}&pagina=1"

        if verbose > 0:
            logger.info("Baixando primeira página...")

        time.sleep(sleep_time)
        first_page_response = session.get(
            first_page_url,
            timeout=30,
            headers={
                'Accept': 'text/html; charset=latin1;',
                'Referer': link_cjsg,
            }
        )
        first_page_response.raise_for_status()

        # Set encoding to latin1 (as in R code)
        first_page_response.encoding = 'latin1'
        first_page_html = first_page_response.text

        # Extract number of pages
        try:
            n_pags = get_n_pags_callback(first_page_html)
            if n_pags == 0:
                logger.info("Nenhum resultado encontrado para a busca")
        except Exception as e:
            debug_dir = os.path.join(download_path, "cjsg_debug")
            if not os.path.isdir(debug_dir):
                os.makedirs(debug_dir)
            debug_file = os.path.join(debug_dir, f"cjsg_primeira_pagina_{timestamp}.html")
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(first_page_html)
            logger.error(
                'Erro ao extrair número de páginas: %s. HTML salvo em: %s',
                str(e),
                debug_file
            )
            raise ValueError(
                f"Erro ao extrair número de páginas: {e}. HTML salvo em: {debug_file}"
            ) from e

        # Save first page
        # Save in latin1 encoding (as received from server) for proper character preservation
        file_name = f"{path}/cjsg_00001.html"
        with open(file_name, 'w', encoding='latin1') as f:
            f.write(first_page_html)

        # Extract conversationId from the page if available
        conversation_id = ''
        try:
            soup = BeautifulSoup(first_page_html, 'html.parser')
            conversation_id_elem = soup.find('input', {'name': 'conversationId'})
            if conversation_id_elem:
                conversation_id = str(conversation_id_elem.get('value', '') or '')
        except Exception:
            pass

    except requests.RequestException as e:
        debug_dir = os.path.join(download_path, "cjsg_debug")
        if not os.path.isdir(debug_dir):
            os.makedirs(debug_dir)
        debug_file = os.path.join(debug_dir, f"cjsg_form_submission_error_{timestamp}.html")
        try:
            if 'response' in locals():
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(response.text if hasattr(response, 'text') else str(response))
        except Exception:
            pass
        logger.error(
            'Erro ao submeter formulário: %s. HTML salvo em: %s',
            str(e),
            debug_file
        )
        raise ValueError(
            f"Erro ao submeter formulário: {e}. HTML salvo em: {debug_file}"
        ) from e

    # If no results, return early
    if n_pags == 0:
        if verbose > 0:
            logger.info("Nenhum resultado encontrado. Retornando apenas a primeira página.")
        return path

    # Determine which pages to download (1-based)
    # Page 1 is already downloaded above, so we only need pages > 1
    if paginas is None:
        paginas_list = list(range(2, n_pags + 1))
    elif isinstance(paginas, range):
        pag_min = paginas.start if paginas.start is not None else 1
        pag_max = min(paginas.stop, n_pags + 1) if paginas.stop is not None else n_pags + 1
        paginas_list = [p for p in range(pag_min, pag_max) if p > 1]
    else:
        # list
        paginas_list = [p for p in paginas if 1 < p <= n_pags]

    if verbose > 0:
        logger.info("Total de páginas: %s", n_pags)
        logger.info("Paginas a serem baixadas: %s", paginas_list)

    # Download remaining pages using requests
    if paginas_list:
        # Include page 1 in the total count for progress bar if it's in the requested range
        if paginas is None:
            page1_in_range = True
        elif isinstance(paginas, range):
            pag_min_for_bar = paginas.start if paginas.start is not None else 1
            page1_in_range = pag_min_for_bar <= 1
        else:
            page1_in_range = 1 in paginas
        total_pages = len(paginas_list) + (1 if page1_in_range else 0)
        initial_count = 1 if page1_in_range else 0
        for pag in tqdm(paginas_list, desc="Baixando documentos", total=total_pages, initial=initial_count):
            time.sleep(sleep_time)
            query = {
                'tipoDeDecisao': 'A' if tipo_decisao == 'acordao' else 'D',
                'pagina': pag,
            }
            # Add conversationId if available
            if conversation_id:
                query['conversationId'] = conversation_id

            u = f"{u_base}cjsg/trocaDePagina.do"
            try:
                r = session.get(
                    u,
                    params=query,
                    timeout=30,
                    headers={
                        'Accept': 'text/html; charset=latin1;',
                        'Referer': f'{u_base}cjsg/resultadoCompleta.do',
                    }
                )
                r.encoding = 'latin1'
                r.raise_for_status()
                file_name = f"{path}/cjsg_{pag:05d}.html"  # noqa: E231
                # Save in latin1 encoding (as received from server) for proper character preservation
                with open(file_name, 'w', encoding='latin1') as f:
                    f.write(r.text)
            except requests.RequestException as e:
                logger.error('Erro ao baixar página %s: %s', pag, str(e))
                raise

    return path
