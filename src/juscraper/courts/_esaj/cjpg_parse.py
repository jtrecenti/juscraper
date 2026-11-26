"""Parse do cjpg do eSAJ (consulta de julgados de primeiro grau), comum a TJSP e TJMS."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from bs4.element import Tag
from tqdm import tqdm

from ...core.exceptions import ColetaParcialError
from ...core.parse_utils import normalizar_texto
from .parse import _extract_pagination_count, _find_pagination_element, _has_zero_results, _raise_page_error

logger = logging.getLogger("juscraper.cjpg_parse")

_CJPG_PAGE_SIZE = 10

MARCA_PAGINA_NAO_BAIXADA = "juscraper-pagina-nao-baixada"
"""``id`` do elemento que ``cjpg_download`` grava no lugar da página que não conseguiu baixar."""

# Chaves que saem do rótulo da página com outro nome: "Magistrado:" vira a
# coluna canônica ``relator``, a mesma do ``cjsg`` e dos demais tribunais.
_CHAVES_CANONICAS = {
    'data_de_disponibilização': 'data_disponibilizacao',
    'magistrado': 'relator',
}


# Célula acima e abaixo das linhas: "Resultados 1 a 10 de 3565472".
_RESUMO_RE = re.compile(r"Resultados?\s+\d+\s+a\s+\d+\s+de\s+(\d+)", re.IGNORECASE)


def _total_do_resumo(soup: BeautifulSoup) -> int | None:
    # A célula tem de ser só o resumo: a de layout, que envolve a página
    # inteira, também contém "Resultados ..." e termina nos links de
    # paginação, de onde um ``\d+$`` tiraria o "1" de uma página só.
    for celula in soup.find_all("td"):
        resumo = _RESUMO_RE.fullmatch(celula.get_text().strip())
        if resumo is not None:
            return int(resumo.group(1))
    return None


def _count_cjpg_result_rows_or_raise(n_rows: int) -> int:
    if 0 < n_rows < _CJPG_PAGE_SIZE:
        return n_rows
    if n_rows >= _CJPG_PAGE_SIZE:
        raise ValueError(
            "A resposta contém uma página completa de resultados sem "
            "marcador de paginação; o HTML pode estar truncado."
        )
    raise ValueError(
        "Não foi possível encontrar o seletor de número de páginas "
        "na resposta HTML. Verifique se a busca retornou resultados "
        "ou se a estrutura da página mudou."
    )


def cjpg_n_results(page_source: str | bytes) -> int:
    """Extracts the total number of results from a CJPG first-page HTML.

    Sibling of :func:`cjpg_n_pags`, which is now a thin wrapper that divides
    by the 10-hits-per-page constant. Used by the ``count_only=True``
    short-circuit in :meth:`~juscraper.courts._esaj.cjpg.EsajCjpgScraper.cjpg` (issue #92).

    Lê o total da célula cujo texto é só "Resultados X a Y de N". Sem ela,
    cai na cascata de seletores e regex do ``cjsg``
    (:func:`juscraper.courts._esaj.parse.cjsg_n_results`), que tolera
    mudanças de layout. A página do cjpg não traz o input oculto com o total
    que o ``cjsg`` lê primeiro. Os marcadores de busca vazia são procurados
    fora das linhas de resultado, porque as sentenças os citam.

    Fallback for "results table present but pagination marker missing":
    counts ``tr.fundocinza1`` rows inside ``divDadosResultado`` when the page
    has fewer than 10 rows. A full page without pagination is ambiguous and
    raises instead of undercounting a potentially truncated response.

    Returns:
        Number of results (0 when the search returned no hits).

    Raises:
        ValueError: When the page reports an error, contains a full results
            page without pagination, or has no known result marker.
    """
    soup = BeautifulSoup(page_source, "html.parser")

    _raise_page_error(soup)
    total = _total_do_resumo(soup)
    if total is not None:
        return total

    # As sentenças ficam nas linhas de resultado e citam "não foram
    # encontrados" ("bens penhoráveis"); os marcadores de contagem ficam
    # fora delas, como no ``cjsg``.
    n_linhas = len(soup.select("#divDadosResultado tr.fundocinza1"))
    for linha in soup.find_all("tr", class_="fundocinza1"):
        linha.extract()
    if _has_zero_results(soup):
        return 0

    page_element = _find_pagination_element(soup)
    if page_element is None:
        return _count_cjpg_result_rows_or_raise(n_linhas)

    pagination_text = page_element.get_text().strip()
    count = _extract_pagination_count(pagination_text)
    if count is None:
        raise ValueError(
            "Não foi possível extrair o número de resultados "
            f"da string: {pagination_text}"
        )
    return count


def cjpg_n_pags(page_source: str | bytes) -> int:
    """Extracts the number of pages from a CJPG first-page HTML.

    Thin wrapper over :func:`cjpg_n_results` that converts result count into
    page count via ``ceil(n_results / 10)`` (CJPG serves 10 hits per page;
    differs from CJSG's 20).
    """
    n_results = cjpg_n_results(page_source)
    if n_results == 0:
        return 0
    return (n_results + _CJPG_PAGE_SIZE - 1) // _CJPG_PAGE_SIZE


def _codigos_inteiro_teor(nome: str | None) -> dict:
    """Os códigos do ``name`` do link de inteiro teor, ``cdProcesso-cdForo-nmAlias-cdDocumento``.

    São as colunas que :meth:`~juscraper.courts._esaj.sentenca.EsajSentencaScraper.baixar_sentencas`
    lê. O ``nm_alias`` vazio, o comum no TJSP, vira ``None``. Um ``name`` com
    outro número de partes só preenche ``cd_processo``, como antes das colunas
    novas.
    """
    partes = str(nome).split('-') if nome else []
    codigos = (partes if len(partes) == 4 else partes[:1]) + [None] * 4
    cd_processo, cd_foro, nm_alias, cd_documento = codigos[:4]
    return {
        'cd_processo': cd_processo,
        'cd_foro': cd_foro,
        'nm_alias': nm_alias or None,
        'cd_documento': cd_documento,
    }


def _extrair_dados_processo(tabela_dados: Tag) -> dict:
    """Extrai identificadores, detalhes e decisão de uma tabela CJPG."""
    dados_processo: dict = {}
    link_inteiro_teor = tabela_dados.find('a', {'style': 'vertical-align: top'})
    if link_inteiro_teor:
        dados_processo.update(_codigos_inteiro_teor(link_inteiro_teor.get('name')))
        span_negrito = link_inteiro_teor.find('span', class_='fonteNegrito')
        dados_processo['id_processo'] = span_negrito.text.strip() if span_negrito is not None else None

    for linha in tabela_dados.find_all('tr', class_='fonte'):
        if linha.find('strong'):
            chave, valor = linha.text.strip().split(':', 1)
            chave = chave.strip().lower().replace(' ', '_').replace('-', '')
            chave = _CHAVES_CANONICAS.get(chave, chave)
            dados_processo[chave] = valor.strip()

    div_decisao = tabela_dados.find('div', {'align': 'justify', 'style': 'display: none;'})
    if div_decisao:
        spans = div_decisao.find_all('span')
        dados_processo['decisao'] = normalizar_texto(spans[-1].get_text(separator=" ", strip=True)) if spans else ''
    return dados_processo


def cjpg_parse_single(path: str | Path) -> pd.DataFrame:
    """Parseia um HTML baixado por :func:`~juscraper.courts._esaj.cjpg_download.cjpg_download`."""
    with Path(path).open('r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    # Página de erro do eSAJ (captcha, por exemplo) não traz resultados, mas
    # não é página sem resultados: levanta, para não sair como página lida.
    _raise_page_error(soup)
    nao_baixada = soup.find(id=MARCA_PAGINA_NAO_BAIXADA)
    if nao_baixada is not None:
        raise ValueError(f"o download falhou: {nao_baixada.get_text()}")
    processos = []
    div_dados_resultado = soup.find('div', {'id': 'divDadosResultado'})
    if div_dados_resultado:
        for tr_processo in div_dados_resultado.find_all('tr', class_='fundocinza1'):
            tabela_dados = tr_processo.find('table')
            if tabela_dados is not None:
                processos.append(_extrair_dados_processo(tabela_dados))
    return pd.DataFrame(processos)


def _parse_diretorio(diretorio: Path) -> pd.DataFrame:
    """Processa cada HTML do diretório; arquivo que falha impede devolver o resto como completo.

    Uma página do CJPG traz até 10 decisões, e a perdida não tem linha onde
    ser marcada. Por isso a falha parcial levanta
    :class:`~juscraper.core.exceptions.ColetaParcialError`, com as páginas
    lidas em ``.resultado``, como no auto-chunk do eSAJ (#459).
    """
    arquivos = [f for f in diretorio.rglob("*.ht*") if f.is_file()]
    resultados = []
    falhas: list[tuple[Path, Exception]] = []
    for arquivo in tqdm(arquivos, desc="Processando documentos"):
        try:
            resultados.append(cjpg_parse_single(arquivo))
        except (ValueError, OSError) as e:
            falhas.append((arquivo, e))
    for arquivo_falho, erro_falho in falhas:
        logger.error('Error processing %s: %s', arquivo_falho, erro_falho)
    resultado = pd.concat(resultados, ignore_index=True) if resultados else pd.DataFrame()
    if not falhas:
        return resultado
    arquivo, erro = falhas[0]
    # Com falha total, devolver vazio confundiria "o layout mudou e nada foi
    # lido" com "a busca não trouxe resultados".
    if not resultados:
        raise ValueError(
            f"Nenhum dos {len(arquivos)} arquivo(s) em {diretorio} pôde ser "
            f"processado. Primeiro erro, em {arquivo.name}: {erro}"
        ) from erro
    # Todas as páginas perdidas vão na mensagem, e não só os exemplos de
    # resumir_falhas: é por ela que se sabe quais baixar de novo.
    raise ColetaParcialError(
        f"cjpg: {len(falhas)} de {len(arquivos)} página(s) falharam: "
        f"{', '.join(arquivo.name for arquivo, _ in falhas)}. Primeiro erro, em {arquivo.name}: {erro}. "
        f"As {len(resultados)} página(s) lidas estão no atributo .resultado do erro; "
        ".falhas traz a exceção de cada página que falhou, na ordem da mensagem.",
        resultado=resultado,
        falhas=[(None, None, falha) for _, falha in falhas],
    ) from erro


def cjpg_parse_manager(path: str | Path) -> pd.DataFrame:
    """Processa os arquivos baixados por ``cjpg_download``.

    ``path`` pode ser um arquivo HTML ou um diretório, percorrido de forma
    recursiva.

    Returns:
        Uma linha por processo. Vazio quando o diretório não tem
            arquivo HTML ou quando nenhuma página traz resultados.

    Raises:
        FileNotFoundError: Quando ``path`` não existe ou não é arquivo nem
            diretório acessível.
        ValueError: Quando o HTML de um arquivo passado diretamente não pôde
            ser interpretado, ou quando todos os arquivos de um diretório
            falharam.
        ColetaParcialError: Quando parte dos arquivos de um diretório falha;
            ``.resultado`` traz as páginas lidas e ``.falhas`` uma tupla
            ``(None, None, excecao)`` por página perdida, nomeada na mensagem.
        OSError: Quando um arquivo passado diretamente não pôde ser lido.
    """
    caminho = Path(path)
    if caminho.is_file():
        return cjpg_parse_single(caminho)
    if caminho.is_dir():
        return _parse_diretorio(caminho)
    raise FileNotFoundError(f"Caminho não encontrado ou inacessível: {caminho}")
