"""
Downloads of processes from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
"""
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from ...core.failures import EXCECOES_DE_FALHA_POR_LINHA, MOTIVO_RESPOSTA_INESPERADA, avisar_falhas, motivo_falha
from ...utils import safe_path_component
from ...utils.cnj import clean_cnj, format_cnj, split_cnj
from .._esaj.pasta import DocumentoIndisponivelError, documentos_vinculados, gravar_pdf, pdf_pela_pasta

logger = logging.getLogger('juscraper.cpopg_download')


class _InvalidProcessCodeError(ValueError):
    """Erro de validação de identificador recebido do CPOPG."""


_TENTATIVAS = 5


# Aviso que o e-SAJ devolve, no lugar do resultado, quando recebe buscas em
# sequência rápida na mesma sessão. O bloqueio passa em alguns segundos.
_AVISO_CONSULTAS_SIMULTANEAS = "multiplas consultas simult"


def _consulta_bloqueada(texto):
    """Indica se a busca voltou com o aviso de consultas simultâneas."""
    return _AVISO_CONSULTAS_SIMULTANEAS in texto.lower()


# A página do processo traz o bloco de movimentações vazio e um botão "Exibir
# movimentações"; o JavaScript do eSAJ busca a lista em
# carregarMovimentacoesAjax.do, cinco linhas por página, e segue o cursor de
# cada página até a última. O fragmento só sai com a sessão que abriu o
# processo: sem ela, o eSAJ devolve a div mensagemErroMovimentacoes.
_ROTA_MOVIMENTACOES = "cpopg/carregarMovimentacoesAjax.do"
_CONTAINER_VAZIO = re.compile(r'<div id="containerMovimentacoes">\s*</div>')
_BOTAO_EXIBIR = re.compile(r'<div id="containerExibirMovimentacoes".*?</div>', re.DOTALL)

PASTA_DOCUMENTOS = "documentos"
"""Subpasta do processo onde ``download_pecas`` grava os PDFs."""


def caminho_do_documento(pasta_processo, cd_documento):
    """``<pasta do processo>/documentos/<cdDocumento>.pdf``; o parser e o download usam o mesmo."""
    return Path(pasta_processo) / PASTA_DOCUMENTOS / f"{safe_path_component(cd_documento, field='cdDocumento')}.pdf"


def validar_download_pecas(method, baixar_movimentacoes, download_pecas):
    """Recusa ``download_pecas`` onde não há links de documento para seguir."""
    if not download_pecas:
        return
    if method != "html":
        raise ValueError("download_pecas=True só funciona com method='html': a API não lista os documentos.")
    if not baixar_movimentacoes:
        raise ValueError(
            "download_pecas=True exige baixar_movimentacoes=True: os documentos vêm das movimentações."
        )


# Todo erro de requests, e não só os de EXCECOES_DE_FALHA_POR_LINHA: um
# ChunkedEncodingError que subisse de _PecasPublicas.baixar faria o retry de
# cpopg_download_html_single refazer o processo inteiro cinco vezes e o
# perder, quando o que falhou foi um documento.
_FALHAS_DE_DOCUMENTO: tuple[type[BaseException], ...] = (
    DocumentoIndisponivelError, requests.RequestException, *EXCECOES_DE_FALHA_POR_LINHA,
)


@dataclass
class _PecasPublicas:
    """PDFs dos documentos públicos das movimentações, pedidos na sessão que as listou.

    O eSAJ só libera documento cuja página de movimentações a sessão já
    carregou; por isso :func:`_completar_documento` chama :meth:`baixar`
    logo depois das movimentações de cada processo, antes de abrir o seguinte.
    Falha de um documento não derruba o processo: ela vai para ``falhas``, o
    PDF fica faltando, e o próximo download com ``download_pecas`` no mesmo
    diretório pede de novo só o que falta.
    """

    sleep_time: float
    falhas: list[str] = field(default_factory=list)

    def baixar(self, html, sessao, url_base, pasta_processo, id_limpo):
        """Grava em ``pasta_processo`` o PDF de cada documento público de ``html`` que ainda não está lá."""
        def get(url):
            time.sleep(self.sleep_time)
            resposta = sessao.get(url)
            resposta.raise_for_status()
            return resposta

        for documento in documentos_vinculados(html):
            destino = caminho_do_documento(pasta_processo, documento.cd_documento)
            if not documento.publico or destino.is_file():
                continue
            try:
                conteudo = pdf_pela_pasta(get, f"{url_base}{documento.url}", url_base, documento.cd_documento)
            except _FALHAS_DE_DOCUMENTO as erro:
                self._falhou(id_limpo, documento.cd_documento, _motivo_do_documento(erro), erro)
                continue
            gravar_pdf(conteudo, destino)

    def _falhou(self, id_limpo, cd_documento, motivo, erro):
        logger.warning("Processo %s, documento %s: %s", id_limpo, cd_documento, erro)
        self.falhas.append(f"{id_limpo}/{cd_documento}: {motivo}")


def _motivo_do_documento(erro):
    """Motivo de falha de um documento; erro de requests fora do vocabulário vira ``resposta_inesperada``."""
    if isinstance(erro, DocumentoIndisponivelError):
        return erro.motivo
    if isinstance(erro, EXCECOES_DE_FALHA_POR_LINHA):
        return motivo_falha(erro)
    return MOTIVO_RESPOSTA_INESPERADA


def cpopg_download_html(
    id_cnj_list,
    session,
    u_base,
    download_path,
    sleep_time=0.5,
    get_links_callback=None,
    *,
    baixar_movimentacoes=True,
    download_pecas=False,
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
    download_pecas: with True, also saves the PDF of each public document of the movements
    """
    pecas = _PecasPublicas(sleep_time) if download_pecas else None
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
                pecas=pecas,
            )
        except (OSError, UnicodeDecodeError, ValueError,
                AttributeError, RuntimeError, requests.RequestException) as e:
            logger.error(
                "Erro ao baixar o processo %s: %s",
                idp,
                e
            )
            continue
    if pecas is not None:
        avisar_falhas(pecas.falhas, "TJSPScraper.cpopg_download", "download(s) de documento público")


def cpopg_download_html_single(
    id_cnj,
    session,
    u_base,
    download_path,
    sleep_time=0.5,
    get_links_callback=None,
    *,
    baixar_movimentacoes=True,
    pecas=None,
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
    pecas: a _PecasPublicas, when the public documents are wanted too
    """
    id_clean = clean_cnj(id_cnj)
    path = f"{download_path}/cpopg/{id_clean}"
    logger.info("Salvando em %s", path)
    if not Path(path).is_dir():
        Path(path).mkdir(parents=True)
    if _ja_baixado(path, baixar_movimentacoes, pecas is not None):
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
    bloqueada = False
    ultimo_erro = None
    for tentativa in range(_TENTATIVAS):
        try:
            r = session.get(u, params=parms)
            bloqueada = _consulta_bloqueada(r.text)
            if bloqueada:
                # Sem esta checagem, a página de aviso (que não tem links)
                # faria o processo parecer inexistente.
                espera = max(sleep_time, 1) * 2 ** tentativa
                logger.warning(
                    "e-SAJ bloqueou a busca do processo %s por consultas "
                    "simultâneas. Tentando novamente em %.1f segundos.",
                    id_cnj,
                    espera,
                )
                time.sleep(espera)
                continue
            if get_links_callback is None:
                raise RuntimeError(
                    "get_links_callback precisa ser"
                    "fornecido para extrair links do HTML."
                )
            links = get_links_callback(r)
            codigos_processo = _extrair_codigos_processo(links)
            _salvar_resultados_html(
                r, links, id_clean, path, session, u_base, codigos_processo,
                baixar_movimentacoes=baixar_movimentacoes, pecas=pecas,
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
        if bloqueada:
            raise RuntimeError(
                f"e-SAJ manteve o bloqueio por consultas simultâneas para o "
                f"processo {id_clean}; aumente o sleep_time."
            )
        raise RuntimeError(
            f"Processo {id_clean}: {_TENTATIVAS} tentativas sem sucesso; último erro: {ultimo_erro}"
        ) from ultimo_erro
    return path


def _ja_baixado(path, baixar_movimentacoes, download_pecas):
    """Indica se a pasta do processo já tem o download completo; ver :func:`_incompleto`."""
    # Os documentos de um processo são gravados juntos no fim
    # (_salvar_resultados_html), então um .html na pasta indica o processo
    # inteiro. O de 0 byte vem de versão que gravava antes de ler a resposta.
    salvos = [
        file for file in Path(path).iterdir() if file.name.endswith('.html') and file.stat().st_size > 0
    ]
    return bool(salvos) and not _incompleto(salvos, baixar_movimentacoes, download_pecas)


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
    pecas=None,
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
        documentos[codigos_processo[0]] = _completar_documento(
            resposta.text, sessao, url_base, codigos_processo[0], caminho, id_limpo,
            baixar_movimentacoes=baixar_movimentacoes, pecas=pecas,
        )
    else:
        for indice, link in enumerate(links):
            # A base termina em barra e o href começa com barra; concatenar
            # gera "//cpopg/show.do", que o e-SAJ responde com 404.
            resposta_documento = sessao.get(urljoin(url_base, link))
            if resposta_documento.status_code != 200:
                raise requests.HTTPError(
                    f"A consulta ao site falhou."
                    f"Processo: {id_limpo}; Código: {codigos_processo[indice]},"  # noqa: E702
                    f"Status code {resposta_documento.status_code}."
                )
            # As movimentações de cada documento saem logo depois do show.do
            # dele, enquanto a sessão está nesse processo.
            documentos[codigos_processo[indice]] = _completar_documento(
                resposta_documento.text, sessao, url_base, codigos_processo[indice], caminho, id_limpo,
                baixar_movimentacoes=baixar_movimentacoes, pecas=pecas,
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


def _completar_documento(
    html, sessao, url_base, codigo_processo, caminho, id_limpo, *, baixar_movimentacoes, pecas,
):
    """Movimentações do documento e, com ``pecas``, os PDFs delas, antes do show.do seguinte.

    Os PDFs saem na sessão que acabou de listar as movimentações: ver :class:`_PecasPublicas`.
    """
    html = _incluir_movimentacoes(
        html, sessao, url_base, codigo_processo, baixar_movimentacoes=baixar_movimentacoes,
    )
    if pecas is not None:
        pecas.baixar(html, sessao, url_base, caminho, id_limpo)
    return html


def _incompleto(salvos, baixar_movimentacoes, download_pecas):
    """Processo salvo que o pedido atual manda baixar de novo.

    Falta o que foi pedido: as movimentações, ou o PDF de algum documento
    público (um que falhou antes, ou um download anterior sem ``download_pecas``).
    """
    if baixar_movimentacoes and any(map(_sem_movimentacoes, salvos)):
        return True
    return download_pecas and any(map(_falta_documento, salvos))


def _falta_documento(arquivo):
    """HTML salvo com documento público cujo PDF não está na pasta do processo."""
    return any(
        documento.publico and not caminho_do_documento(arquivo.parent, documento.cd_documento).is_file()
        for documento in documentos_vinculados(arquivo.read_text(encoding='utf-8'))
    )


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
