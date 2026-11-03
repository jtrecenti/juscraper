"""
Downloads of processes from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
"""
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from ...utils import safe_path_component
from ...utils.cnj import clean_cnj, format_cnj, split_cnj

logger = logging.getLogger('juscraper.cpopg_download')


class _InvalidProcessCodeError(ValueError):
    """Erro de validação de identificador recebido do CPOPG."""


_TENTATIVAS = 5


# A página do processo traz o bloco de movimentações vazio e um botão "Exibir
# movimentações"; o JavaScript do eSAJ busca a lista em
# carregarMovimentacoesAjax.do, cinco linhas por página, e segue o cursor de
# cada página até a última. O fragmento só sai com a sessão que abriu o
# processo: sem ela, o eSAJ devolve a div mensagemErroMovimentacoes.
_ROTA_MOVIMENTACOES = "cpopg/carregarMovimentacoesAjax.do"
_CONTAINER_VAZIO = re.compile(r'<div id="containerMovimentacoes">\s*</div>')
_BOTAO_EXIBIR = re.compile(r'<div id="containerExibirMovimentacoes".*?</div>', re.DOTALL)


def cpopg_download_html(
    id_cnj_list,
    session,
    u_base,
    download_path,
    sleep_time=0.5,
    get_links_callback=None,
    *,
    baixar_movimentacoes=True,
):
    """
    Downloads processes in HTML from the TJSP Consulta de Processos Originários do Primeiro Grau (CPOPG).
    id_cnj_list: list of CNJs
    session: requests.Session authenticated
    u_base: base URL of ESAJ
    download_path: base directory to save
    sleep_time: interval between attempts
    get_links_callback: function to extract links from HTML
    baixar_movimentacoes: with False, skips the movements requests
    """
    n_items = len(id_cnj_list)
    for idp in tqdm(id_cnj_list, total=n_items, desc="Baixando processos"):
        try:
            cpopg_download_html_single(
                idp,
                session,
                u_base,
                download_path,
                sleep_time,
                get_links_callback,
                baixar_movimentacoes=baixar_movimentacoes,
            )
        except (OSError, UnicodeDecodeError, ValueError,
                AttributeError, RuntimeError, requests.RequestException) as e:
            logger.error(
                "Erro ao baixar o processo %s: %s",
                idp,
                e
            )
            continue


def cpopg_download_html_single(
    id_cnj,
    session,
    u_base,
    download_path,
    sleep_time=0.5,
    get_links_callback=None,
    *,
    baixar_movimentacoes=True,
):
    """
    Downloads a process in HTML from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
    id_cnj: CNJ of the process
    session: requests.Session authenticated
    u_base: base URL of ESAJ
    download_path: base directory to save
    sleep_time: interval between attempts
    get_links_callback: function to extract links from HTML
    baixar_movimentacoes: with False, skips the movements requests
    """
    id_clean = clean_cnj(id_cnj)
    path = f"{download_path}/cpopg/{id_clean}"
    logger.info("Salvando em %s", path)
    if not Path(path).is_dir():
        Path(path).mkdir(parents=True)
    # Os documentos de um processo são gravados juntos no fim
    # (_salvar_resultados_html), então um .html na pasta indica o processo
    # inteiro. O de 0 byte vem de versão que gravava antes de ler a resposta.
    salvos = [
        file for file in Path(path).iterdir() if file.name.endswith('.html') and file.stat().st_size > 0
    ]
    if salvos and not (baixar_movimentacoes and any(map(_sem_movimentacoes, salvos))):
        logger.info("O processo %s ja foi baixado.", id_clean)
        return path
    time.sleep(sleep_time)
    id_format = format_cnj(id_clean)
    p = split_cnj(id_clean)
    u = f"{u_base}cpopg/search.do"
    parms = {
        'conversationId': '',
        'cbPesquisa': 'NUMPROC',
        'numeroDigitoAnoUnificado': f"{p['num']}-{p['dv']}.{p['ano']}",
        'foroNumeroUnificado': p['orgao'],
        'dadosConsulta.valorConsultaNuUnificado': id_format,
        'dadosConsulta.valorConsulta': '',
        'dadosConsulta.tipoNuProcesso': 'UNIFICADO'
    }
    ultimo_erro = None
    for _ in range(_TENTATIVAS):
        try:
            r = session.get(u, params=parms)
            if get_links_callback is None:
                raise RuntimeError(
                    "get_links_callback precisa ser"
                    "fornecido para extrair links do HTML."
                )
            links = get_links_callback(r)
            codigos_processo = _extrair_codigos_processo(links)
            _salvar_resultados_html(
                r, links, id_clean, path, session, u_base, codigos_processo,
                baixar_movimentacoes=baixar_movimentacoes,
            )
            break
        except _InvalidProcessCodeError:
            # O código inválido veio da resposta do tribunal e não muda com
            # nova tentativa; sai antes do except genérico, que capturaria o
            # ValueError e repetiria a busca quatro vezes à toa.
            raise
        except (OSError, UnicodeDecodeError, ValueError,
                AttributeError, requests.RequestException) as e:
            ultimo_erro = e
            logger.error(
                "Erro ao conectar ao site (processo %s)."
                "Tentando novamente em %.1f segundos. (%s)",
                id_cnj,
                sleep_time,
                e
            )
            time.sleep(sleep_time)
    else:
        raise RuntimeError(
            f"Processo {id_clean}: {_TENTATIVAS} tentativas sem sucesso; último erro: {ultimo_erro}"
        ) from ultimo_erro
    return path


def _extrair_codigos_processo(links):
    """Extrai e valida códigos para uso nos nomes dos arquivos."""
    codigos_processo = []
    for link in links:
        parametros = parse_qs(urlparse(link).query)
        codigos = parametros.get('processo.codigo', [])
        if not codigos:
            raise RuntimeError(f"Link sem 'processo.codigo': {link}")
        try:
            codigo_seguro = safe_path_component(codigos[0], field="processo.codigo")
        except ValueError as exc:
            raise _InvalidProcessCodeError(str(exc)) from exc
        codigos_processo.append(codigo_seguro)
    return codigos_processo


def _salvar_resultados_html(
    resposta, links, id_limpo, caminho, sessao, url_base, codigos_processo,
    *,
    baixar_movimentacoes=True,
):
    """Salva a busca ou os documentos individuais.

    Os documentos ficam em memória até o último ser baixado e só então são
    gravados, cada um por arquivo temporário renomeado: uma falha no meio não
    deixa na pasta parte dos documentos, nem um ``.html`` vazio, e o teste de
    "já baixado" em :func:`cpopg_download_html_single` continua valendo.
    """
    if len(links) == 0:
        logger.error("Nenhum link encontrado para o processo %s.", id_limpo)
        raise RuntimeError(f"Nenhum link encontrado para o processo {id_limpo}.")
    documentos = {}
    if len(links) == 1:
        documentos[codigos_processo[0]] = _incluir_movimentacoes(
            resposta.text, sessao, url_base, codigos_processo[0],
            baixar_movimentacoes=baixar_movimentacoes,
        )
    else:
        for indice, link in enumerate(links):
            resposta_documento = sessao.get(f"{url_base}{link}")
            if resposta_documento.status_code != 200:
                raise requests.HTTPError(
                    f"A consulta ao site falhou."
                    f"Processo: {id_limpo}; Código: {codigos_processo[indice]},"  # noqa: E702
                    f"Status code {resposta_documento.status_code}."
                )
            # As movimentações de cada documento saem logo depois do show.do
            # dele, enquanto a sessão está nesse processo.
            documentos[codigos_processo[indice]] = _incluir_movimentacoes(
                resposta_documento.text, sessao, url_base, codigos_processo[indice],
                baixar_movimentacoes=baixar_movimentacoes,
            )
    # .tmp, e não .html.tmp: o glob do parse ('*.[hj][st]*') pegaria o segundo.
    destinos = {Path(caminho) / f"{id_limpo}_{codigo}.html": html for codigo, html in documentos.items()}
    temporarios = []
    try:
        # Todos os .tmp primeiro: um erro de disco no segundo documento não
        # pode deixar o primeiro já renomeado para .html.
        for destino, html in destinos.items():
            temporario = destino.with_suffix('.tmp')
            temporarios.append(temporario)
            temporario.write_text(html, encoding='utf-8')
    except OSError:
        for temporario in temporarios:
            temporario.unlink(missing_ok=True)
        raise
    for destino in destinos:
        logger.info("Salvando em %s", destino)
        destino.with_suffix('.tmp').replace(destino)


def _sem_movimentacoes(arquivo):
    """HTML salvo sem as movimentações, com ou sem o botão (baixar_movimentacoes=False o tira)."""
    return _CONTAINER_VAZIO.search(arquivo.read_text(encoding='utf-8')) is not None


def _incluir_movimentacoes(html, sessao, url_base, codigo_processo, *, baixar_movimentacoes=True):
    """Grava no HTML do processo a lista completa de movimentações.

    O arquivo fica como a página no navegador depois de "Exibir movimentações"
    e de "Mais" até a última página, e o parser lê só o arquivo. Página sem o
    bloco vazio (formato antigo, com ``tabelaTodasMovimentacoes``) sai como
    veio. Com ``baixar_movimentacoes=False`` sai só o botão: o parser avisa
    quando acha o botão, e quem desligou o download não precisa do aviso. O
    container continua vazio, e ``_sem_movimentacoes`` o reconhece.
    """
    if not _CONTAINER_VAZIO.search(html):
        return html
    if not baixar_movimentacoes:
        return _BOTAO_EXIBIR.sub('', html, count=1)
    primeira = _pagina_movimentacoes(sessao, url_base, codigo_processo, cursor=None)
    bloco = BeautifulSoup(primeira, 'html.parser')
    if bloco.find('tbody', id='tabelaPrimeiraPaginaMovimentacoes') is None:
        # Sem a tabela, o arquivo gravado leria como processo sem
        # movimentações; ValueError faz o retry refazer a busca.
        raise ValueError(
            f"Movimentações do processo {codigo_processo}: a primeira página veio fora do formato conhecido."
        )
    entrada_cursor = bloco.find('input', id='cursorMovimentacoesPaginado')
    if entrada_cursor is not None:
        _anexar_paginas_seguintes(bloco, sessao, url_base, codigo_processo, entrada_cursor.get('value'))
    paginacao = bloco.find('div', id='divLinkMovimentacoesPaginado')
    if paginacao is not None:
        paginacao.decompose()
    html = _BOTAO_EXIBIR.sub('', html, count=1)
    return _CONTAINER_VAZIO.sub(
        lambda _: f'<div id="containerMovimentacoes">{bloco}</div>', html, count=1,
    )


def _anexar_paginas_seguintes(bloco, sessao, url_base, codigo_processo, cursor):
    """Segue o cursor e anexa as linhas de cada página em ``tabelaOutrasPaginasMovimentacoes``."""
    outras_paginas = bloco.find('tbody', id='tabelaOutrasPaginasMovimentacoes')
    vistos = set()
    while cursor:
        if outras_paginas is None or cursor in vistos:
            raise RuntimeError(
                f"Movimentações do processo {codigo_processo}: a paginação não avançaria "
                f"(cursor {cursor!r})."
            )
        vistos.add(cursor)
        pagina = BeautifulSoup(
            f"<table><tbody>{_pagina_movimentacoes(sessao, url_base, codigo_processo, cursor)}</tbody></table>",
            'html.parser',
        )
        linhas = pagina.find_all('tr', class_='containerMovimentacao')
        if not linhas:
            raise RuntimeError(
                f"Movimentações do processo {codigo_processo}: página sem linhas no cursor {cursor!r}."
            )
        outras_paginas.extend(linhas)
        linha_cursor = pagina.find('tr', id='trCursorMovimentacoes')
        cursor = linha_cursor.get('data-cursor') if linha_cursor else None
    if outras_paginas is not None:
        del outras_paginas['style']


def _pagina_movimentacoes(sessao, url_base, codigo_processo, cursor):
    """Uma página do carregarMovimentacoesAjax.do; ``cursor=None`` pede a primeira."""
    parametros = {'processo.codigo': codigo_processo}
    if cursor:
        parametros['cursor'] = cursor
    resposta = sessao.get(f"{url_base}{_ROTA_MOVIMENTACOES}", params=parametros)
    if resposta.status_code != 200:
        raise requests.HTTPError(
            f"Movimentações do processo {codigo_processo}: status code {resposta.status_code}."
        )
    if 'mensagemErroMovimentacoes' in resposta.text:
        # ValueError: o retry de cpopg_download_html_single refaz a busca,
        # que reabre o processo na sessão.
        raise ValueError(
            f"O eSAJ recusou as movimentações do processo {codigo_processo}."
        )
    return resposta.text


def cpopg_download_api(
    id_cnj_list,
    session,
    api_base,
    download_path,
    *,
    baixar_movimentacoes=True,
):
    """
    Downloads processes in JSON from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
    id_cnj_list: list of CNJs
    session: requests.Session authenticated
    api_base: base URL of ESAJ API
    download_path: base directory to save
    baixar_movimentacoes: with False, skips the movimentacao endpoint
    """
    n_items = len(id_cnj_list)
    for idp in tqdm(id_cnj_list, total=n_items, desc="Baixando processos"):
        try:
            cpopg_download_api_single(
                idp, session, api_base, download_path, baixar_movimentacoes=baixar_movimentacoes,
            )
        except (OSError, UnicodeDecodeError, ValueError,
                AttributeError, requests.RequestException) as e:
            logger.error(
                "Erro ao baixar o processo %s: %s",
                idp,
                e
            )
            continue


def cpopg_download_api_single(
    id_cnj,
    session,
    api_base,
    download_path,
    *,
    baixar_movimentacoes=True,
):
    """
    Downloads a process in JSON from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
    id_cnj: CNJ of the process
    session: requests.Session authenticated
    api_base: base URL of ESAJ API
    download_path: base directory to save
    baixar_movimentacoes: with False, skips the movimentacao endpoint
    """
    endpoint = 'processo/cpopg/search/numproc/'
    id_clean = clean_cnj(id_cnj)
    u = f"{api_base}{endpoint}{id_clean}"
    # id_clean vem de clean_cnj (so digitos), seguro como componente de path.
    path = f"{download_path}/cpopg/{id_clean}"
    if not Path(path).is_dir():
        Path(path).mkdir(parents=True)
    r = session.get(u)
    if r.status_code != 200:
        raise requests.HTTPError(
            f"A consulta à API falhou."
            f"Status code {r.status_code}."
        )
    with Path(f"{path}/{id_clean}.json").open('w', encoding='utf-8') as f:
        f.write(r.text)
    json_response = r.json()
    if not json_response:
        logger.error("Nenhum dado encontrado para o processo %s.", id_clean)
        return ''
    for processo in json_response:
        cd_processo = processo['cdProcesso']
        cd_processo_safe = safe_path_component(cd_processo, field="cdProcesso")
        endpoint_basicos = 'processo/cpopg/dadosbasicos/'
        u_basicos = f"{api_base}{endpoint_basicos}{cd_processo}"
        r_basicos = session.post(u_basicos, json={'cdProcesso': cd_processo})
        if r_basicos.status_code != 200:
            raise requests.HTTPError(
                f"A consulta à API falhou."
                f"Status code {r_basicos.status_code}."
            )
        with (Path(path) / f"{cd_processo_safe}_basicos.json").open('w', encoding='utf-8') as f:
            f.write(r_basicos.text)
        componentes = ['partes', 'movimentacao', 'incidente', 'audiencia']
        if not baixar_movimentacoes:
            componentes.remove('movimentacao')
        for comp in componentes:
            endpoint_comp = f"processo/cpopg/{comp}/{cd_processo}"
            r_comp = session.get(f"{api_base}{endpoint_comp}")
            if r_comp.status_code == 200:
                with (Path(path) / f"{cd_processo_safe}_{comp}.json").open('w', encoding='utf-8') as f:
                    f.write(r_comp.text)
            else:
                raise requests.HTTPError(
                    f"Erro ao buscar {comp} para o processo {cd_processo}."
                    f"Status: {r_comp.status_code}"
                )
    return path
