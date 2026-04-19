"""
Download of results from the TJAC Consulta de Julgados de Segundo Grau (CJSG).
TJAC uses the eSAJ platform (same as TJSP).
"""
import os
import time
from datetime import datetime
import logging

import requests
import urllib3
from tqdm import tqdm

from juscraper.utils.params import to_br_date

logger = logging.getLogger("juscraper.tjac.cjsg_download")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://esaj.tjac.jus.br/"


def cjsg_download(
    pesquisa: str,
    download_path: str,
    sleep_time: float = 1.0,
    ementa: str | None = None,
    numero_recurso: str | None = None,
    classe: str | None = None,
    assunto: str | None = None,
    comarca: str | None = None,
    orgao_julgador: str | None = None,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    origem: str = "T",
    tipo_decisao: str = "acordao",
    paginas: 'int | list | range | None' = None,
    get_n_pags_callback=None,
) -> str:
    """Downloads HTML files from the TJAC CJSG search results pages.

    Parameters
    ----------
    pesquisa : str
        Search term for full-text search.
    download_path : str
        Base directory for saving files.
    sleep_time : float
        Time to wait between requests.
    ementa : str, optional
        Filter by ementa text.
    numero_recurso : str, optional
        Appeal number filter.
    classe : str, optional
        Procedural class filter (tree selection value).
    assunto : str, optional
        Subject filter (tree selection value).
    comarca : str, optional
        District filter.
    orgao_julgador : str, optional
        Judging body filter (tree selection value).
    data_julgamento_inicio, data_julgamento_fim : str, optional
        Judgment date range (dd/mm/yyyy).
    data_publicacao_inicio, data_publicacao_fim : str, optional
        Publication date range (dd/mm/yyyy).
    origem : str
        Origin: ``"T"`` for 2nd degree (default), ``"R"`` for recursal courts.
    tipo_decisao : str
        ``"acordao"`` or ``"monocratica"``.
    paginas : int, list, range, or None
        Page range to download (1-based). None = all.
    get_n_pags_callback : callable
        Function to extract total pages from first-page HTML.

    Returns
    -------
    str
        Path to directory containing downloaded HTML files.
    """
    if get_n_pags_callback is None:
        raise ValueError("get_n_pags_callback is required to extract the number of pages.")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = os.path.join(download_path, "cjsg", timestamp)
    os.makedirs(path, exist_ok=True)

    session = requests.Session()
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
    })
    session.verify = False

    tipo_param = "A" if tipo_decisao == "acordao" else "D"

    body = {
        "conversationId": "",
        "dados.buscaInteiroTeor": pesquisa,
        "dados.pesquisarComSinonimos": "S",
        "dados.buscaEmenta": ementa or "",
        "dados.nuProcOrigem": numero_recurso or "",
        "dados.nuRegistro": "",
        "agenteSelectedEntitiesList": "",
        "contadoragente": "0",
        "contadorMaioragente": "0",
        "codigoCr": "",
        "codigoTr": "",
        "nmAgente": "",
        "juizProlatorSelectedEntitiesList": "",
        "contadorjuizProlator": "0",
        "contadorMaiorjuizProlator": "0",
        "codigoJuizCr": "",
        "codigoJuizTr": "",
        "nmJuiz": "",
        "classesTreeSelection.values": classe or "",
        "classesTreeSelection.text": "",
        "assuntosTreeSelection.values": assunto or "",
        "assuntosTreeSelection.text": "",
        "comarcaSelectedEntitiesList": "",
        "contadorcomarca": "1",
        "contadorMaiorcomarca": "1",
        "cdComarca": comarca or "",
        "nmComarca": "",
        "secoesTreeSelection.values": orgao_julgador or "",
        "secoesTreeSelection.text": "",
        "dados.dtJulgamentoInicio": to_br_date(data_julgamento_inicio) or "",
        "dados.dtJulgamentoFim": to_br_date(data_julgamento_fim) or "",
        "dados.dtRegistroInicio": "",
        "dados.dtRegistroFim": "",
        "dados.dtPublicacaoInicio": to_br_date(data_publicacao_inicio) or "",
        "dados.dtPublicacaoFim": to_br_date(data_publicacao_fim) or "",
        "dados.origensSelecionadas": origem,
        "tipoDecisaoSelecionados": tipo_param,
        "dados.ordenacao": "dtPublicacao",
    }

    link_cjsg = f"{BASE_URL}cjsg/resultadoCompleta.do"

    logger.info("Submetendo formulário de busca...")
    response = session.post(link_cjsg, data=body, timeout=30, allow_redirects=True)
    response.raise_for_status()

    first_page_url = f"{BASE_URL}cjsg/trocaDePagina.do?tipoDeDecisao={tipo_param}&pagina=1"
    time.sleep(sleep_time)
    first_page_response = session.get(
        first_page_url,
        timeout=30,
        headers={"Accept": "text/html; charset=latin1;", "Referer": link_cjsg},
    )
    first_page_response.raise_for_status()
    first_page_response.encoding = "latin1"
    first_page_html = first_page_response.text

    n_pags = get_n_pags_callback(first_page_html)
    if n_pags == 0:
        logger.info("Nenhum resultado encontrado para a busca.")
        with open(os.path.join(path, "cjsg_00001.html"), "w", encoding="latin1") as f:
            f.write(first_page_html)
        return path

    with open(os.path.join(path, "cjsg_00001.html"), "w", encoding="latin1") as f:
        f.write(first_page_html)

    if paginas is None:
        paginas_list = list(range(2, n_pags + 1))
    elif isinstance(paginas, range):
        pag_max = min(paginas.stop, n_pags + 1)
        paginas_list = [p for p in range(paginas.start, pag_max) if p > 1]
    else:
        paginas_list = [p for p in paginas if 1 < p <= n_pags]

    logger.info("Total de páginas: %s. Baixando: %s", n_pags, len(paginas_list) + 1)

    if paginas_list:
        page1_in_range = paginas is None or (
            isinstance(paginas, range) and paginas.start <= 1
        ) or (isinstance(paginas, list) and 1 in paginas)
        total_pages = len(paginas_list) + (1 if page1_in_range else 0)
        initial = 1 if page1_in_range else 0

        for pag in tqdm(paginas_list, desc="Baixando CJSG TJAC", total=total_pages, initial=initial):
            time.sleep(sleep_time)
            u = f"{BASE_URL}cjsg/trocaDePagina.do"
            params = {"tipoDeDecisao": tipo_param, "pagina": pag}
            for attempt in range(3):
                try:
                    r = session.get(
                        u,
                        params=params,
                        timeout=30,
                        headers={
                            "Accept": "text/html; charset=latin1;",
                            "Referer": f"{BASE_URL}cjsg/resultadoCompleta.do",
                        },
                    )
                    r.encoding = "latin1"
                    r.raise_for_status()
                    break
                except requests.RequestException as exc:
                    if attempt == 2:
                        logger.error("Erro ao baixar página %s após 3 tentativas: %s", pag, exc)
                        raise
                    logger.warning("Tentativa %s falhou para página %s: %s", attempt + 1, pag, exc)
                    time.sleep(sleep_time * (attempt + 1))

            with open(os.path.join(path, f"cjsg_{pag:05d}.html"), "w", encoding="latin1") as f:
                f.write(r.text)

    return path
