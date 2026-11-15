"""
Downloads processes from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOSG).
"""
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from ...core.failures import MOTIVO_ENTRADA_INVALIDA, MOTIVO_NAO_ENCONTRADO
from ...utils import safe_path_component
from ...utils.cnj import clean_cnj, format_cnj, split_cnj
from .._esaj.acordao import RespostaInesperadaError, busca_sem_informacoes, paginas_movimentacoes, parse_cd_processo
from ._falhas import cnj_invalido, motivo_do_processo, registrar_falhas
from .cpopg_download import _TIMEOUT

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

    Returns:
        (dict[str, str]): ``{CNJ formatado: motivo}`` dos processos que ficaram
            sem arquivo, no vocabulário de :mod:`juscraper.core.failures`. O
            processo que a consulta de 2º grau não mostra ("Não existem
            informações disponíveis") sai ``nao_encontrado``. Vazio quando todos
            foram baixados. As falhas ficam gravadas em ``<download_path>/cposg``,
            de onde ``cposg_parse_manager`` as lê; o ``UserWarning`` delas sai de
            ``TJSPScraper.cposg_download``.
    """
    if isinstance(id_cnj_list, str):
        id_cnj_list = [id_cnj_list]
    # A pasta existe mesmo sem processo encontrado: sem ela, cposg_parse_manager
    # leria o download_path inteiro, inclusive os arquivos do cpopg.
    Path(download_path, 'cposg').mkdir(parents=True, exist_ok=True)
    falhas = {}
    for id_cnj in tqdm(id_cnj_list, desc="Baixando processos"):
        cnj = format_cnj(id_cnj, strict=False)
        if cnj_invalido(id_cnj):
            falhas[cnj] = MOTIVO_ENTRADA_INVALIDA
            continue
        try:
            if _cposg_download_html_single(id_cnj, session, u_base, download_path) is None:
                falhas[cnj] = MOTIVO_NAO_ENCONTRADO
        except (OSError, UnicodeDecodeError, ValueError, AttributeError,
                RuntimeError, RespostaInesperadaError, requests.RequestException) as e:
            logger.error("Erro ao baixar o processo %s: %s", id_cnj, e)
            falhas[cnj] = motivo_do_processo(e)
        # Também depois de um erro: o eSAJ bloqueia buscas em sequência rápida.
        time.sleep(sleep_time)
    registrar_falhas(Path(download_path, 'cposg'), id_cnj_list, falhas)
    return falhas


def _cposg_download_html_single(id_cnj, session, u_base, download_path):
    id_clean = clean_cnj(id_cnj)
    p = split_cnj(id_clean)
    id_format = format_cnj(id_clean)
    u = f"{u_base}cposg/search.do"
    # 1. Acessar página inicial para garantir cookies válidos
    open_url = f"{u_base}cposg/open.do?gateway=true"
    session.get(open_url, timeout=_TIMEOUT)
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
    r = _get(session, u, params=params)
    soup = BeautifulSoup(r.text, 'html.parser')
    if _sem_informacoes(soup, id_format):
        return None
    codigos = _codigos_da_busca(soup)
    if codigos is None:
        # Caso 3: resposta simples — o id vem do input[name=cdProcesso] (nao
        # de processo.codigo como nos casos 1/2), dai field="cdProcesso".
        documentos = {
            parse_cd_processo(r.text) or "simples": _incluir_movimentacoes(r.text, session, u_base, id_format),
        }
    else:
        documentos = {}
        for codigo in codigos:
            safe_codigo = safe_path_component(codigo, field="processo.codigo")
            pagina = _get(session, f"{u_base}cposg/show.do?processo.codigo={codigo}").text
            documentos[safe_codigo] = _incluir_movimentacoes(pagina, session, u_base, id_format)
    if not documentos:
        raise RuntimeError(f"Processo {id_format}: a busca não listou nenhum processo.")
    # Os arquivos só são gravados depois do último documento: a falha de um
    # incidente não deixa os outros na pasta, lidos como o processo completo.
    # id_clean vem de clean_cnj (so digitos), seguro como componente de path.
    path = Path(download_path, 'cposg', id_clean)
    path.mkdir(parents=True, exist_ok=True)
    for codigo, html in documentos.items():
        (path / f"{id_clean}_cd_processo_{codigo}.html").write_text(html, encoding='utf-8')
    return str(path)


def _codigos_da_busca(soup):
    """``processo.codigo`` da listagem (caso 1) ou do modal de incidentes (caso 2); ``None`` fora dos dois."""
    if soup.find('div', id='listagemDeProcessos'):
        codigos = []
        for a in soup.select('a.linkProcesso'):
            link = str(a['href'])
            codigo = parse_qs(urlparse(link).query).get('processo.codigo', [])
            if not codigo:
                raise RuntimeError(f"Link sem 'processo.codigo': {link}")
            codigos.append(codigo[0])
        return codigos
    if soup.find('div', id='modalIncidentes'):
        return [str(i['value']) for i in soup.select('input#processoSelecionado')]
    return None


def _get(session: requests.Session, url: str, **kwargs: Any) -> requests.Response:
    """GET com o timeout do eSAJ; status de erro levanta ``requests.HTTPError``, e a página não vira processo."""
    resposta: requests.Response = session.get(url, timeout=_TIMEOUT, **kwargs)
    resposta.raise_for_status()
    return resposta


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
        resposta: requests.Response = session.get(url, params=params, timeout=_TIMEOUT)
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
