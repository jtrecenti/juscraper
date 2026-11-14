"""
Downloads processes from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOSG).
"""
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from ...core.avisos import avisar
from ...utils import safe_path_component
from ...utils.cnj import clean_cnj, format_cnj, split_cnj
from .._esaj.acordao import RespostaInesperadaError, busca_sem_informacoes, paginas_movimentacoes, parse_cd_processo

logger = logging.getLogger('juscraper.cposg_download')

# A página do processo traz o container de movimentações vazio e o link
# "Exibir movimentações"; o JavaScript do eSAJ busca a lista em
# carregarMovimentacoesAjax.do, cinco linhas por página, com a sessão que
# abriu o processo.
_CONTAINER_VAZIO = re.compile(r'<div id="containerMovimentacoesAjax"[^>]*>\s*</div>')
_LINK_EXIBIR = re.compile(r'<div id="divExibirMovimentacoes".*?</div>', re.DOTALL)
_CD_PROCESSO_MOVIMENTACOES = re.compile(r"cdProcessoMovimentacoes = '([^']+)'")


def cposg_download_html(id_cnj_list, session, u_base, download_path, sleep_time=0.5):
    """
    Downloads the HTML of one or more processes from the CPOSG.
    Returns a list of paths if list, or a single path if string.

    Processo que a consulta de 2º grau não mostra ("Não existem informações
    disponíveis") não gera arquivo e sai num ``UserWarning`` ao fim; se for o
    único, a função devolve ``[]``.
    """
    if isinstance(id_cnj_list, str):
        id_cnj_list = [id_cnj_list]
    # A pasta existe mesmo sem processo encontrado: sem ela, cposg_parse_manager
    # leria o download_path inteiro, inclusive os arquivos do cpopg.
    Path(download_path, 'cposg').mkdir(parents=True, exist_ok=True)
    paths = []
    nao_encontrados = []
    for id_cnj in tqdm(id_cnj_list, desc="Baixando processos"):
        try:
            path = _cposg_download_html_single(id_cnj, session, u_base, download_path)
        except (OSError, UnicodeDecodeError, ValueError, AttributeError,
                RuntimeError, RespostaInesperadaError, requests.RequestException) as e:
            logger.error("Erro ao baixar o processo %s: %s", id_cnj, e)
            continue
        if path is None:
            nao_encontrados.append(id_cnj)
        else:
            paths.append(path)
        time.sleep(sleep_time)
    if nao_encontrados:
        avisar(
            f"cposg: a consulta de 2º grau não mostra {len(nao_encontrados)} processo(s), que fica(m) "
            f"fora do resultado: {', '.join(nao_encontrados)}. O número pode não existir no 2º grau, "
            "ou o processo está em segredo de justiça, que o eSAJ não mostra na consulta pública."
        )
    if not paths and not nao_encontrados:
        raise RuntimeError("Nenhum processo foi baixado com sucesso.")
    return paths if len(paths) != 1 else paths[0]


def _cposg_download_html_single(id_cnj, session, u_base, download_path):
    id_clean = clean_cnj(id_cnj)
    p = split_cnj(id_clean)
    id_format = format_cnj(id_clean)
    u = f"{u_base}cposg/search.do"
    # 1. Acessar página inicial para garantir cookies válidos
    open_url = f"{u_base}cposg/open.do?gateway=true"
    session.get(open_url)
    # 2. Montar parâmetros corretos
    params = {
        'conversationId': '',
        'paginaConsulta': '1',
        'localPesquisa.cdLocal': '-1',
        'cbPesquisa': 'NUMPROC',
        'tipoNuProcesso': 'UNIFICADO',
        'numeroDigitoAnoUnificado': f"{p['num']}-{p['dv']}.{p['ano']}",
        'foroNumeroUnificado': p['orgao'],
        'dePesquisaNuUnificado': id_format,
        'dePesquisa': '',
        'uuidCaptcha': '',
        'pbEnviar': 'Pesquisar'
    }
    r = session.get(u, params=params)
    soup = BeautifulSoup(r.text, 'html.parser')
    if _sem_informacoes(soup, id_format):
        return None
    # id_clean vem de clean_cnj (so digitos), seguro como componente de path.
    path = f"{download_path}/cposg/{id_clean}"
    if not Path(path).is_dir():
        Path(path).mkdir(parents=True)
    # 3. Tratar tipos de resposta
    # Caso 1: listagem de processos
    if soup.find('div', id='listagemDeProcessos'):
        links = [str(a['href']) for a in soup.select('a.linkProcesso')]
        for link in links:
            codigos = parse_qs(urlparse(link).query).get('processo.codigo', [])
            if not codigos:
                raise RuntimeError(f"Link sem 'processo.codigo': {link}")
            codigo = codigos[0]
            safe_codigo = safe_path_component(codigo, field="processo.codigo")
            show_url = f"{u_base}cposg/show.do?processo.codigo={codigo}"
            html = _incluir_movimentacoes(session.get(show_url).text, session, u_base, id_format)
            file_name = Path(path) / f"{id_clean}_cd_processo_{safe_codigo}.html"
            with file_name.open('w', encoding='utf-8') as f:
                f.write(html)
    # Caso 2: incidentes/modal
    elif soup.find('div', id='modalIncidentes'):
        codigos = [str(i['value']) for i in soup.select('input#processoSelecionado')]
        for codigo in codigos:
            safe_codigo = safe_path_component(codigo, field="processo.codigo")
            show_url = f"{u_base}cposg/show.do?processo.codigo={codigo}"
            html = _incluir_movimentacoes(session.get(show_url).text, session, u_base, id_format)
            file_name = Path(path) / f"{id_clean}_cd_processo_{safe_codigo}.html"
            with file_name.open('w', encoding='utf-8') as f:
                f.write(html)
    # Caso 3: resposta simples — o id vem do input[name=cdProcesso] (nao de
    # processo.codigo como nos casos 1/2), dai field="cdProcesso".
    else:
        codigo_part = parse_cd_processo(r.text) or "simples"
        html = _incluir_movimentacoes(r.text, session, u_base, id_format)
        file_name = Path(path) / f"{id_clean}_cd_processo_{codigo_part}.html"
        with file_name.open('w', encoding='utf-8') as f:
            f.write(html)
    return path


def _sem_informacoes(soup, id_cnj):
    """``True`` quando a busca diz que não há o processo; outra mensagem do eSAJ levanta ``RuntimeError``.

    A página de processo não traz ``#mensagemRetorno``. Sem esta checagem, a
    mensagem seria gravada como processo e lida como lista vazia.
    """
    if busca_sem_informacoes(soup):
        return True
    mensagem = soup.find(id='mensagemRetorno')
    if mensagem is None:
        return False
    raise RuntimeError(f"Processo {id_cnj}: o eSAJ respondeu à busca com \"{mensagem.get_text(' ', strip=True)}\".")


def _incluir_movimentacoes(html, session, u_base, id_cnj):
    """Grava no HTML do processo a lista completa de movimentações.

    O arquivo fica como a página no navegador depois de "Exibir movimentações"
    e de "Mais" até a última página, e o parser lê só o arquivo. Página sem o
    container vazio (formato antigo, com ``tabelaTodasMovimentacoes``, ou
    resposta sem processo) sai como veio. Página fora do formato levanta
    ``ValueError``: gravada, ela leria como processo sem movimentações, ou
    com a lista cortada.
    """
    if not _CONTAINER_VAZIO.search(html):
        return html
    cd_processo = _CD_PROCESSO_MOVIMENTACOES.search(html)
    if cd_processo is None:
        raise ValueError(f"Processo {id_cnj}: a página não traz o cdProcesso das movimentações.")

    def get(url: str, params: dict) -> requests.Response:
        resposta: requests.Response = session.get(url, params=params, timeout=60)
        resposta.raise_for_status()
        return resposta

    paginas = paginas_movimentacoes(
        get, f"{u_base}cposg/carregarMovimentacoesAjax.do", id_cnj, cd_processo.group(1),
    )
    bloco = BeautifulSoup(next(paginas), 'html.parser')
    tabela = bloco.find('tbody', id='tabelaMovimentacoesAjax')
    if tabela is None:
        raise ValueError(f"Movimentações do processo {id_cnj}: a primeira página veio fora do formato conhecido.")
    for numero, pagina in enumerate(paginas, start=2):
        linhas = BeautifulSoup(f"<table><tbody>{pagina}</tbody></table>", 'html.parser')
        # Página seguinte sem a linha de metadados (erro, sessão perdida)
        # encerraria a paginação em silêncio, com a lista cortada.
        if linhas.find('tr', id='metaPaginaMovimentacoes') is None:
            raise ValueError(f"Movimentações do processo {id_cnj}: a página {numero} veio fora do formato conhecido.")
        tabela.extend(linhas.find_all('tr', class_='movimentacaoProcesso'))
    links_paginacao = bloco.find('div', id='divLinksMovimentacoesPaginadas')
    if links_paginacao is not None:
        links_paginacao.decompose()
    html = _LINK_EXIBIR.sub('', html, count=1)
    return _CONTAINER_VAZIO.sub(
        lambda _: f'<div id="containerMovimentacoesAjax">{bloco}</div>', html, count=1,
    )
