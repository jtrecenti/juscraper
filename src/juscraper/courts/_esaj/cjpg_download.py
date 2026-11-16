"""Download do cjpg do eSAJ (consulta de julgados de primeiro grau).

TJSP e TJMS o usam por :class:`juscraper.courts._esaj.cjpg.EsajCjpgScraper`
(#487).
"""
from __future__ import annotations

import html
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from tqdm import tqdm

from ...utils.cnj import clean_cnj
from ...utils.pagination import paginas_no_intervalo
from .cjpg_parse import MARCA_PAGINA_NAO_BAIXADA, cjpg_n_pags
from .prazos import TENTATIVAS as _TENTATIVAS
from .prazos import TIMEOUT as _TIMEOUT

__all__ = ["cjpg_download", "fetch_cjpg_first_page"]

logger = logging.getLogger("juscraper.cjpg_download")


def _save_debug_html(response: requests.Response, download_path: str, error: Exception) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
    debug_dir = Path(download_path) / "cjpg_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / f"cjpg_primeira_pagina_{timestamp}.html"
    debug_file.write_text(response.text, encoding="utf-8")
    logging.getLogger("juscraper.cjpg_download").error(
        "Erro ao extrair número de páginas: %s. HTML salvo em: %s",
        str(error),
        debug_file,
    )
    return debug_file


def _extract_page_count(
    response: requests.Response,
    download_path: str,
) -> int:
    try:
        return cjpg_n_pags(response.content)
    except Exception as error:
        debug_file = _save_debug_html(response, download_path, error)
        raise ValueError(
            f"Erro ao extrair número de páginas: {error}. HTML salvo em: {debug_file}"
        ) from error


def _normalize_pages(
    paginas: list[int] | range | None, n_pags: int, u_base: str, *, tribunal: str | None = None,
) -> list[int]:
    """Páginas pedidas dentro de ``1..n_pags``, sem repetição; ``None`` vale todas.

    As de fora saem em aviso no logger de ``tribunal``; chamadas diretas do
    helper ainda podem derivar a sigla do host de ``u_base``.
    """
    sigla = tribunal or (urlparse(u_base).hostname or "").removesuffix(".jus.br").rsplit(".", 1)[-1].upper()
    return paginas_no_intervalo(paginas, n_pags, tribunal=sigla)


def _save_page(path: Path, page: int, html: str) -> None:
    path.joinpath(f"cjpg_{page:05d}.html").write_text(html, encoding="utf-8")


def _baixar_pagina(session: requests.Session, url: str, page: int, sleep_time: float) -> str:
    """HTML da página ``page``, com até ``_TENTATIVAS`` pedidos, como no ``cpopg``.

    Status de erro conta como falha: a página de erro do eSAJ, gravada,
    seria lida como página sem resultados. Esgotadas as tentativas, devolve
    uma página com a marca :data:`MARCA_PAGINA_NAO_BAIXADA` e o último erro,
    que :func:`~juscraper.courts._esaj.cjpg_parse.cjpg_parse_single` recusa:
    as demais páginas seguem, e a perdida sobe no ``ColetaParcialError`` do
    parse (#460).
    """
    ultimo_erro: requests.RequestException | None = None
    for tentativa in range(_TENTATIVAS):
        if tentativa:
            time.sleep(sleep_time)
        try:
            resposta = session.get(url, timeout=_TIMEOUT)
            resposta.raise_for_status()
        except requests.RequestException as erro:
            ultimo_erro = erro
            logger.warning("cjpg: página %s, tentativa %s de %s: %s", page, tentativa + 1, _TENTATIVAS, erro)
        else:
            return resposta.text
    mensagem = f"página {page} não baixada após {_TENTATIVAS} tentativas; último erro: {ultimo_erro}"
    logger.error("cjpg: %s", mensagem)
    return f'<p id="{MARCA_PAGINA_NAO_BAIXADA}">{html.escape(mensagem)}</p>\n'


def fetch_cjpg_first_page(  # noqa: PLR0913 - um parâmetro por filtro do formulário
    *,
    pesquisa: str,
    session: requests.Session,
    u_base: str,
    classe: str | None = None,
    assunto: str | None = None,
    vara: str | None = None,
    id_processo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> requests.Response:
    """Run the CJPG initial GET and return the raw :class:`requests.Response`.

    Shared by :func:`cjpg_download` (continues into paginated download) and
    by the ``count_only=True`` short-circuit in :meth:`~juscraper.courts._esaj.cjpg.EsajCjpgScraper.cjpg`
    (issue #92), which only needs the first-page HTML.

    Returns the response (not just ``.text``) so that the download path can
    persist it to disk and the count-only path can extract ``n_results``
    from ``.text`` without an extra request.
    """
    id_processo_str = clean_cnj(id_processo) if id_processo is not None else ''

    query = {
        'conversationId': '',
        'dadosConsulta.pesquisaLivre': pesquisa,
        'tipoNumero': 'UNIFICADO',
        'numeroDigitoAnoUnificado': id_processo_str[:15],
        'foroNumeroUnificado': id_processo_str[-4:],
        'dadosConsulta.nuProcesso': id_processo_str,
        'classeTreeSelection.values': classe,
        'assuntoTreeSelection.values': assunto,
        'dadosConsulta.dtInicio': data_inicio,
        'dadosConsulta.dtFim': data_fim,
        'varasTreeSelection.values': vara,
        'dadosConsulta.ordenacao': 'DESC'
    }

    return session.get(f"{u_base}cjpg/pesquisar.do", params=query, timeout=_TIMEOUT)


def cjpg_download(  # noqa: PLR0913 - um parâmetro por filtro do formulário
    pesquisa: str,
    session: requests.Session,
    u_base: str,
    download_path: str,
    sleep_time: float = 0.5,
    classe: str | None = None,
    assunto: str | None = None,
    vara: str | None = None,
    id_processo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    paginas: list[int] | range | None = None,
    tribunal: str | None = None,
) -> str:
    """Download cases from the eSAJ first-instance jurisprudence search (TJSP, TJMS).

    Internal helper — the public scraper entry point
    (:meth:`~juscraper.courts._esaj.cjpg.EsajCjpgScraper.cjpg_download`) runs the
    ``_validate_pesquisa`` hook and pydantic validation before calling this function. Direct callers
    must validate ``pesquisa`` upstream.

    ``classe``/``assunto``/``vara`` chegam ja como CSV (ou ``None``); a coercao
    de ``int``/``list`` -> CSV acontece no schema (:class:`InputCJPGEsaj`) via
    :data:`IdFiltro`. Refs #232.

    Cada página a partir da 2 tem até cinco pedidos. A que falha em todos
    é gravada com o último erro, e o parse a recusa (``cjpg_parse_manager``):
    o parse do diretório levanta ``ColetaParcialError`` com as demais.

    Raises:
        ValueError: If the page count cannot be extracted from the first-page
            HTML. The response is saved for diagnosis before raising.
    """
    r0 = fetch_cjpg_first_page(
        pesquisa=pesquisa,
        session=session,
        u_base=u_base,
        classe=classe,
        assunto=assunto,
        vara=vara,
        id_processo=id_processo,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    n_pags = _extract_page_count(r0, download_path)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    path = Path(download_path) / "cjpg" / timestamp
    path.mkdir(parents=True, exist_ok=True)

    if n_pags == 0:
        _save_page(path, 1, r0.text)
        return str(path)

    paginas_list = _normalize_pages(paginas, n_pags, u_base, tribunal=tribunal)

    first_page_in_range = 1 in paginas_list
    if first_page_in_range:
        _save_page(path, 1, r0.text)

    remaining = [p for p in paginas_list if p > 1]
    for page in tqdm(remaining, desc="Baixando documentos", total=len(paginas_list), initial=int(first_page_in_range)):
        time.sleep(sleep_time)
        u = f"{u_base}cjpg/trocarDePagina.do?pagina={page}&conversationId="
        _save_page(path, page, _baixar_pagina(session, u, page, sleep_time))
    return str(path)
