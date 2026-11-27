"""Capture samples for TJSP across all public endpoints.

TJSP exposes four public methods (``cjsg``, ``cjpg``, ``cpopg``, ``cposg``).
This script exercises each flow against the live eSAJ host and dumps raw
responses under ``tests/tjsp/samples/<endpoint>/``.

Run from repo root::

    python -m tests.fixtures.capture.tjsp

Override the CNJ of test via ``--cnj`` if the default is retired::

    python -m tests.fixtures.capture.tjsp --cnj 1000149-71.2024.8.26.0346

The script is intentionally linear — each endpoint is a separate function,
and ``main()`` calls them in order. If one flow breaks (e.g., eSAJ returns
503), the others still produce samples.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Comment

import juscraper as jus
from juscraper.courts._esaj.acordao import paginas_movimentacoes
from juscraper.courts.tjsp.cpopg_parse import _split_party_cell
from tests.tjsp.test_arvore_contract import NO_ESPERADO

from ._util import (
    TJSP_CHROME_HEADERS,
    build_session,
    capture_acordao_samples,
    capture_cjsg_samples,
    dump,
    fetch_cjpg_page1,
    fetch_cjsg_pages,
    make_tjsp_cjsg_body,
    samples_dir_for,
)

logger = logging.getLogger(__name__)

ESAJ_BASE = "https://esaj.tjsp.jus.br/"

# CNJ used by the existing integration tests (tests/tjsp/test_cpopg.py).
# If it disappears from the TJSP index, pass --cnj to override.
DEFAULT_CNJ = "1000149-71.2024.8.26.0346"

# Número sem processo no TJSP, para a busca "Não existem informações disponíveis".
CPOPG_CNJ_INEXISTENTE = "0000001-12.2024.8.26.0100"


# ---------- cjsg ---------------------------------------------------------

def capture_cjsg() -> None:
    """Capture cjsg samples via the shared helper with the TJSP body/headers."""
    capture_cjsg_samples(
        tribunal="tjsp",
        base_url=ESAJ_BASE,
        headers=TJSP_CHROME_HEADERS,
        body_builder=make_tjsp_cjsg_body,
        monocratica_query="usucapiao extraordinario predio rural familia",
    )
    # Ementa curta com a palavra "resultados" na 1a página (observado em
    # 14/11/2026 com "direito" e baixar_sg=False): a contagem não pode tomar
    # a célula da ementa pela paginação.
    _, resps = fetch_cjsg_pages(
        build_session(headers=TJSP_CHROME_HEADERS), ESAJ_BASE, "direito",
        body_builder=lambda pesquisa, **kw: make_tjsp_cjsg_body(pesquisa, baixar_sg=False, **kw),
    )
    if "BONIFICAÇÃO POR RESULTADOS" not in resps[0].text:
        # Sem a ementa, o sample deixaria de exercitar a regressão.
        logger.info("[tjsp] cjsg ementa_com_resultados: a 1a página mudou; sample mantido")
    else:
        dump(samples_dir_for("tjsp", "cjsg") / "ementa_com_resultados.html", resps[0].content)
        logger.info("[tjsp] cjsg ementa_com_resultados ('direito', baixar_sg=False) → saved")
    capture_cjsg_sem_ementa()
    capture_cjsg_numero_recurso()


# Recurso com um acórdão só (julgado em 01/10/2026), usado no filtro ``numero_recurso``.
CJSG_NUMERO_RECURSO = "1507541-25.2025.8.26.0425"


def capture_cjsg_numero_recurso() -> None:
    """Grava ``cjsg/numero_recurso.html``: busca só pelo número do recurso.

    O filtro vai em ``dados.nuProcOrigem``. Em 27/11/2026, a busca trouxe uma
    linha, com o próprio recurso no ``processo``.
    """
    _, resps = fetch_cjsg_pages(
        build_session(headers=TJSP_CHROME_HEADERS), ESAJ_BASE, "",
        body_builder=lambda pesquisa, **kw: make_tjsp_cjsg_body(
            pesquisa, numero_recurso=CJSG_NUMERO_RECURSO, **kw
        ),
    )
    linhas = BeautifulSoup(resps[0].text, "html.parser").find_all("tr", class_="fundocinza1")
    if len(linhas) != 1 or CJSG_NUMERO_RECURSO not in resps[0].text:
        # Sem o recurso como única linha, o sample deixaria de mostrar o filtro.
        logger.info("[tjsp] cjsg numero_recurso: %s linhas; sample mantido", len(linhas))
        return
    dump(samples_dir_for("tjsp", "cjsg") / "numero_recurso.html", resps[0].content)
    logger.info("[tjsp] cjsg numero_recurso (%s) → saved", CJSG_NUMERO_RECURSO)


def capture_cjsg_sem_ementa() -> None:
    """Grava ``cjsg/sem_ementa.html``: 1a página com acórdãos com e sem ementa.

    O acórdão sem ementa vem sem a linha ``Ementa:``; o ``N/A`` do eSAJ fica
    só no texto oculto de "ementa sem formatação". Em 26/11/2026, esta busca
    trouxe 9 de 20 linhas assim.
    """
    _, resps = fetch_cjsg_pages(
        build_session(headers=TJSP_CHROME_HEADERS), ESAJ_BASE, "roubo",
        body_builder=lambda pesquisa, **kw: make_tjsp_cjsg_body(
            pesquisa, data_inicio="01/03/2021", data_fim="03/03/2021", **kw
        ),
    )
    linhas = BeautifulSoup(resps[0].text, "html.parser").find_all("tr", class_="fundocinza1")
    com_ementa = sum(
        bool(linha.find("strong", string=lambda texto: "Ementa:" in (texto or ""))) for linha in linhas
    )
    if not 0 < com_ementa < len(linhas):
        # Sem as duas formas na página, o sample deixaria de exercitar o caso.
        logger.info("[tjsp] cjsg sem_ementa: %s de %s linhas com ementa; sample mantido", com_ementa, len(linhas))
        return
    dump(samples_dir_for("tjsp", "cjsg") / "sem_ementa.html", resps[0].content)
    logger.info("[tjsp] cjsg sem_ementa: %s de %s linhas sem ementa → saved", len(linhas) - com_ementa, len(linhas))


# ---------- cjpg ---------------------------------------------------------

def _fetch_cjpg_page_n(session: requests.Session, page: int) -> requests.Response:
    url = f"{ESAJ_BASE}cjpg/trocarDePagina.do"
    params: dict[str, str] = {"pagina": str(page), "conversationId": ""}
    r = session.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r


def capture_cjpg_single_page() -> None:
    """Grava ``cjpg/single_page.html``: busca cujos resultados cabem numa página de 10.

    Em 26/11/2026, "jurimétrica" trouxe 2 sentenças. A busca antiga
    ("usucapiao extraordinario predio rural familia juizado") já não trazia
    nenhuma. Confere pelas linhas da página, e não por ``cjpg_n_results``.
    """
    session = build_session(headers=TJSP_CHROME_HEADERS)
    resposta = fetch_cjpg_page1(session, ESAJ_BASE, "jurimétrica")
    linhas = BeautifulSoup(resposta.content, "html.parser").select("#divDadosResultado tr.fundocinza1")
    if not 0 < len(linhas) < 10:
        # Com 10 linhas pode haver página 2, e o sample deixaria de exercitar o caso.
        logger.info("[tjsp] cjpg single_page: %s linhas na 1a página; sample mantido", len(linhas))
        return
    dump(samples_dir_for("tjsp", "cjpg") / "single_page.html", resposta.content)
    logger.info("[tjsp] cjpg single_page ('jurimétrica', %s resultado(s)) → saved", len(linhas))


def capture_cjpg_sentenca_sem_bens() -> None:
    """Grava ``cjpg/sentenca_nao_foram_encontrados.html``: sentenças que citam "não foram encontrados".

    A frase é um dos marcadores de busca sem resultado. Em 26/11/2026, a busca
    trouxe "Resultados 1 a 10 de 102853", e a contagem dava 0 porque lia o
    texto das sentenças.
    """
    session = build_session(headers=TJSP_CHROME_HEADERS)
    resposta = fetch_cjpg_page1(session, ESAJ_BASE, '"não foram encontrados bens"')
    if "não foram encontrados" not in resposta.text:
        # Sem a frase, o sample deixaria de exercitar o caso.
        logger.info("[tjsp] cjpg sentenca_nao_foram_encontrados: frase ausente na 1a página; sample mantido")
        return
    dump(samples_dir_for("tjsp", "cjpg") / "sentenca_nao_foram_encontrados.html", resposta.content)
    logger.info("[tjsp] cjpg sentenca_nao_foram_encontrados → saved")


def capture_cjpg() -> None:
    """Capture cjpg samples (typical multi-page, single-page, no-results).

    Each scenario runs in its own try/except so a flaky 500 on one request
    (common on the TJSP cjpg paginator) does not abort the rest. Uses a
    fresh session per scenario — shared cookies across unrelated queries
    make the server drop state more often than not.
    """
    dest = samples_dir_for("tjsp", "cjpg")

    # Typical multi-page — tried once with a fresh session and a sleep
    # between page 1 and page 2, because the paginator is stateful.
    try:
        session = build_session(headers=TJSP_CHROME_HEADERS)
        r1 = fetch_cjpg_page1(session, ESAJ_BASE, "dano moral")
        dump(dest / "results_normal_page_01.html", r1.content)
        time.sleep(1.5)
        r2 = _fetch_cjpg_page_n(session, 2)
        dump(dest / "results_normal_page_02.html", r2.content)
        logger.info("[tjsp] cjpg typical ('dano moral') → 2 pages saved")
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("[tjsp] cjpg typical FAILED: %s", exc)

    try:
        capture_cjpg_single_page()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("[tjsp] cjpg single_page FAILED: %s", exc)

    try:
        capture_cjpg_sentenca_sem_bens()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("[tjsp] cjpg sentenca_nao_foram_encontrados FAILED: %s", exc)

    try:
        session = build_session(headers=TJSP_CHROME_HEADERS)
        r_none = fetch_cjpg_page1(session, ESAJ_BASE, "juscraper_probe_zero_hits_xyzqwe")
        dump(dest / "no_results.html", r_none.content)
        logger.info("[tjsp] cjpg no_results → saved")
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("[tjsp] cjpg no_results FAILED: %s", exc)


# ---------- cpopg html ---------------------------------------------------

def capture_cpopg_html(cnj: str) -> None:
    """Capture cpopg samples for ``method='html'``.

    Fetches ``search.do`` for ``cnj`` and the ``show.do`` of the first link
    returned (saved as ``show_real.html``, which no test reads).
    """
    dest = samples_dir_for("tjsp", "cpopg")
    session = build_session(headers=TJSP_CHROME_HEADERS)

    # search
    num, dv = cnj.split("-")[0], cnj.split("-")[1][:2]
    ano = cnj.split(".")[1]
    orgao = cnj.split(".")[-1]
    params = {
        "conversationId": "",
        "cbPesquisa": "NUMPROC",
        "numeroDigitoAnoUnificado": f"{num}-{dv}.{ano}",
        "foroNumeroUnificado": orgao,
        "dadosConsulta.valorConsultaNuUnificado": cnj,
        "dadosConsulta.valorConsulta": "",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
    }
    r_search = session.get(f"{ESAJ_BASE}cpopg/search.do", params=params, timeout=60)
    r_search.raise_for_status()
    dump(dest / "search.html", r_search.content)
    logger.info("[tjsp] cpopg html search for %s → saved", cnj)

    # Número sem processo: "Não existem informações disponíveis" (#460).
    params_inexistente = {
        **params,
        "numeroDigitoAnoUnificado": "0000001-12.2024",
        "foroNumeroUnificado": "0100",
        "dadosConsulta.valorConsultaNuUnificado": CPOPG_CNJ_INEXISTENTE,
    }
    r_inexistente = session.get(f"{ESAJ_BASE}cpopg/search.do", params=params_inexistente, timeout=60)
    r_inexistente.raise_for_status()
    dump(dest / "search_sem_informacoes.html", r_inexistente.content)
    logger.info("[tjsp] cpopg html search for %s → saved", CPOPG_CNJ_INEXISTENTE)

    # parse the search response to discover the processo.codigo param
    # (simplified: regex over the HTML; scraper uses BeautifulSoup but we
    # just need the codes for sample capture)
    codigos = re.findall(r"processo\.codigo=([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        logger.info("[tjsp] cpopg html: no processo.codigo in search response for %s", cnj)
        return
    # fetch show.do for first code only — extra codes add noise
    cd = codigos[0]
    r_show = session.get(
        f"{ESAJ_BASE}cpopg/show.do",
        params={"processo.codigo": cd},
        timeout=60,
    )
    r_show.raise_for_status()
    dump(dest / "show_real.html", r_show.content)
    logger.info("[tjsp] cpopg html show for codigo=%s → saved", cd)


# Processo com "Outros assuntos" no bloco maisDetalhes, que vira a coluna
# ``outros_assuntos``. Em 26/11/2026, o show.do dele trazia o campo.
CPOPG_CNJ_OUTROS_ASSUNTOS = "1009367-76.2017.8.26.0344"

# Nome de ente público, que fica no sample (como "Fazenda Pública do Estado de São Paulo").
_ENTE_PUBLICO = re.compile(r"fazenda|minist[ée]rio p[úu]blico|procuradoria|prefeitura|munic[íi]pio|defensoria", re.I)
# Lista de advogados das publicações: "Advogados(s): Nome (OAB 123/SP), Outro (OAB 456/SP)".
_ADVOGADO_PUBLICACAO = re.compile(r"([^,:()\n]+?) \(OAB \d+/")


def pseudonimizar_cpopg(html: str) -> str:
    """Troca por fictícios os nomes das partes e dos representantes, e zera a OAB.

    Os nomes saem da tabela de partes e das listas de advogados das
    publicações; nada fica fixo no script. Cada parte vira "Parte Ficticia N"
    e cada representante, "Advogado Ficticio N", em todo o HTML e sem
    distinguir maiúsculas. Entes públicos e o juiz ficam.
    """
    partes: list[str] = []
    advogados: list[str] = []
    soup = BeautifulSoup(html, "html.parser")
    for tabela in soup.find_all("table", id=("tableTodasPartes", "tablePartesPrincipais")):
        for linha in tabela.find_all("tr"):
            celulas = linha.find_all("td")
            if len(celulas) >= 2:
                nome, representantes = _split_party_cell(celulas[1])
                partes.append(nome)
                advogados.extend(representantes)
    advogados.extend(nome.strip() for nome in _ADVOGADO_PUBLICACAO.findall(html))
    trocas: dict[str, str] = {}
    for nomes, rotulo in ((partes, "Parte Ficticia"), (advogados, "Advogado Ficticio")):
        for nome in dict.fromkeys(nomes):
            if nome and not _ENTE_PUBLICO.search(nome) and nome.lower() not in map(str.lower, trocas):
                trocas[nome] = f"{rotulo} {sum(v.startswith(rotulo) for v in trocas.values()) + 1}"
    # O nome mais longo primeiro: "Fulano de Tal" não pode quebrar "Fulano de Tal Junior".
    for real in sorted(trocas, key=len, reverse=True):
        html = re.sub(re.escape(real), trocas[real], html, flags=re.IGNORECASE)
    return re.sub(r"\(OAB \d+/", "(OAB 000000/", html)


def capture_cpopg_outros_assuntos() -> None:
    """Grava ``cpopg/show_outros_assuntos.html`` como o ``cpopg_download`` o salva.

    O download junta à página as movimentações que o eSAJ carrega à parte
    (``carregarMovimentacoesAjax.do``); o arquivo é o que o parser lê na
    pasta de download. Os nomes saem trocados por :func:`pseudonimizar_cpopg`.
    """
    with tempfile.TemporaryDirectory() as pasta:
        scraper = jus.scraper("tjsp", download_path=pasta)
        scraper.cpopg_download(CPOPG_CNJ_OUTROS_ASSUNTOS)
        salvos = list(Path(pasta).rglob("*.html"))
        if len(salvos) != 1:
            logger.info("[tjsp] cpopg outros_assuntos: %s arquivos salvos; sample mantido", len(salvos))
            return
        html = pseudonimizar_cpopg(salvos[0].read_bytes().decode("utf-8"))
    if "Outros assuntos" not in html:
        # Sem o campo, o sample deixaria de exercitar a coluna outros_assuntos.
        logger.warning("[tjsp] cpopg outros_assuntos: a página não traz mais o campo; sample mantido")
        return
    dump(samples_dir_for("tjsp", "cpopg") / "show_outros_assuntos.html", html.encode("utf-8"))
    logger.info("[tjsp] cpopg outros_assuntos (%s) → saved", CPOPG_CNJ_OUTROS_ASSUNTOS)


# ---------- cposg html ---------------------------------------------------

def capture_cposg_html(cnj: str) -> None:
    """Capture cposg samples for ``method='html'``.

    Flow: GET ``open.do?gateway=true`` (warm up cookies) → GET ``search.do``
    → GET ``show.do`` per link. Only the common ``listagemDeProcessos``
    variant is captured automatically; modal (``modalIncidentes``) and
    simple variants require specific CNJs — capture those manually and
    save as ``search_modal.html`` / ``search_simple.html`` if needed.
    """
    dest = samples_dir_for("tjsp", "cposg")
    session = build_session(headers=TJSP_CHROME_HEADERS)

    r_open = session.get(f"{ESAJ_BASE}cposg/open.do", params={"gateway": "true"}, timeout=60)
    r_open.raise_for_status()
    dump(dest / "open.html", r_open.content)
    logger.info("[tjsp] cposg html open → saved")

    num, dv = cnj.split("-")[0], cnj.split("-")[1][:2]
    ano = cnj.split(".")[1]
    orgao = cnj.split(".")[-1]
    params = {
        "conversationId": "",
        "paginaConsulta": "1",
        "localPesquisa.cdLocal": "-1",
        "cbPesquisa": "NUMPROC",
        "tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": f"{num}-{dv}.{ano}",
        "foroNumeroUnificado": orgao,
        "dePesquisaNuUnificado": cnj,
        "dePesquisa": "",
        "uuidCaptcha": "",
        "pbEnviar": "Pesquisar",
    }
    r_search = session.get(f"{ESAJ_BASE}cposg/search.do", params=params, timeout=60)
    r_search.raise_for_status()
    dump(dest / "search_listagem.html", r_search.content)
    logger.info("[tjsp] cposg html search for %s → saved", cnj)

    codigos = re.findall(r"processo\.codigo=([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        # Try alternative selector for the "simple" response variant
        codigos = re.findall(r"cdProcesso[\"']\s+value=[\"']([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        logger.info("[tjsp] cposg html: no process code found in search response for %s", cnj)
        return

    # A página do processo deixa as movimentações para o carregarMovimentacoesAjax.do,
    # que só responde à sessão que abriu o processo (aqui, a da busca).
    cd_movimentacoes = re.search(r"cdProcessoMovimentacoes = '([A-Za-z0-9]+)'", r_search.text)
    if cd_movimentacoes:
        paginas = paginas_movimentacoes(
            lambda url, **kw: session.get(url, timeout=60, **kw),
            f"{ESAJ_BASE}cposg/carregarMovimentacoesAjax.do", cnj, cd_movimentacoes.group(1),
        )
        for numero, pagina in enumerate(paginas, start=1):
            dump(dest / f"movimentacoes_pagina_{numero}.html", pagina.encode("utf-8"))
            logger.info("[tjsp] cposg html movimentações página %s → saved", numero)

    cd = codigos[0]
    r_show = session.get(
        f"{ESAJ_BASE}cposg/show.do",
        params={"processo.codigo": cd},
        timeout=60,
    )
    r_show.raise_for_status()
    dump(dest / "show.html", r_show.content)
    logger.info("[tjsp] cposg html show for codigo=%s → saved", cd)


# ---------- acordao (movimentacao) --------------------------------------

# Apelação julgada em 21/09/2026 com dois embargos (incidentes 50000 e 50001,
# cada um com cdProcesso próprio no modal). O cjsg dá 28/10/2026 para o
# acórdão dos embargos 50000, registrado em 30/10; 22/09/2026 passa pelas
# certidões antes de chegar a ele.
ACORDAO_CASOS = [
    ("modal_incidentes", "1502870-48.2020.8.26.0161", "21/09/2026"),
    ("modal_incidentes", "1502870-48.2020.8.26.0161", "22/09/2026"),
    ("modal_incidentes", "1502870-48.2020.8.26.0161", "28/10/2026"),
]


def capture_acordao() -> None:
    """Capture the acórdão route, plus the page for a document not yet listed.

    ``verificarAcessoMovimentacao.do`` só libera documento que a sessão já
    listou; sem as movimentações carregadas ele devolve uma página HTML.
    """
    capture_acordao_samples("tjsp", ACORDAO_CASOS)
    cnj = "1502870-48.2020.8.26.0161"
    session = build_session(headers=TJSP_CHROME_HEADERS)
    session.get(f"{ESAJ_BASE}cposg/search.do", params={
        "conversationId": "", "paginaConsulta": "1", "localPesquisa.cdLocal": "-1",
        "cbPesquisa": "NUMPROC", "tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": cnj[:15], "foroNumeroUnificado": cnj[-4:],
        "dePesquisaNuUnificado": cnj, "dePesquisa": "", "uuidCaptcha": "", "pbEnviar": "Pesquisar",
    }, timeout=60)
    r = session.get(f"{ESAJ_BASE}cposg/verificarAcessoMovimentacao.do", params={
        "cdDocumento": "16", "origemRecurso": "M", "cdProcesso": "RI009HVDD0000", "conversationId": "",
    }, timeout=60)
    dump(samples_dir_for("tjsp", "acordao") / "verificar_acesso_nao_listado.html", r.content)
    logger.info("[tjsp] acordao: verificarAcesso sem movimentações carregadas → saved")


# ---------- documentos públicos (peças do cpopg e sentença do cjpg) -------

# O processo dos samples cpopg/movimentacoes_pagina_{1,2,3}.html: a página 1 traz
# um documento com senha (190277046) e um público, a 3 outro público.
DOCUMENTOS_CD_PROCESSO = "1W001DU0E0000"
DOCUMENTOS_PUBLICOS = ("186579563", "175634201")
# O primeiro resultado de cjpg/results_normal_page_01.html (atributo ``name``).
SENTENCA_NAME = "3I0006RUY0000-126--167379827"


def _redirecionamento(session: requests.Session, url: str, params: dict) -> str:
    """``Location`` do 302 que leva à página da pasta digital."""
    resposta = session.get(url, params=params, allow_redirects=False, timeout=60)
    if resposta.status_code != 302:
        raise RuntimeError(f"{url}: esperava 302, veio {resposta.status_code}")
    return resposta.headers["Location"]


def capture_documentos() -> None:
    """Capture the pasta digital pages behind the public documents.

    Saves under ``tests/tjsp/samples/documentos/``: for each public document
    of the cpopg samples, the ``Location`` of ``abrirDocumentoVinculadoMovimentacao.do``
    and the pasta page it leads to; the refusal for a document that the
    session has not listed; and the same pair for the cjpg sentence. The
    pasta pages carry the process number and the document tree, no names.
    The PDF itself is not saved: the tests only need a body starting with
    ``%PDF``.
    """
    dest = samples_dir_for("tjsp", "documentos")
    redirecionamentos: dict[str, str] = {}
    abrir = f"{ESAJ_BASE}cpopg/abrirDocumentoVinculadoMovimentacao.do"

    # Sem listar as movimentações: a recusa.
    session = build_session(headers=TJSP_CHROME_HEADERS)
    resposta = session.get(
        abrir, params={"processo.codigo": DOCUMENTOS_CD_PROCESSO, "cdDocumento": DOCUMENTOS_PUBLICOS[0]}, timeout=60,
    )
    dump(dest / "acesso_nao_validado.html", resposta.content)
    time.sleep(1.5)

    session = build_session(headers=TJSP_CHROME_HEADERS)
    session.get(f"{ESAJ_BASE}cpopg/show.do", params={"processo.codigo": DOCUMENTOS_CD_PROCESSO}, timeout=60)
    cursor: str | None = None
    while True:
        time.sleep(1.5)
        params = {"processo.codigo": DOCUMENTOS_CD_PROCESSO}
        if cursor:
            params["cursor"] = cursor
        pagina = session.get(f"{ESAJ_BASE}cpopg/carregarMovimentacoesAjax.do", params=params, timeout=60).text
        achado = re.search(r'id="cursorMovimentacoesPaginado"[^>]*value="([^"]*)"|data-cursor="([^"]*)"', pagina)
        cursor = next((g for g in achado.groups() if g), None) if achado else None
        if not cursor:
            break
    for cd in DOCUMENTOS_PUBLICOS:
        time.sleep(1.5)
        local = _redirecionamento(session, abrir, {"processo.codigo": DOCUMENTOS_CD_PROCESSO, "cdDocumento": cd})
        redirecionamentos[f"movimentacao_{cd}"] = local
        time.sleep(1.5)
        dump(dest / f"pasta_{cd}.html", session.get(local, timeout=60).content)

    session = build_session(headers=TJSP_CHROME_HEADERS)
    cd_processo, cd_foro, nm_alias, cd_documento = SENTENCA_NAME.split("-")
    local = _redirecionamento(
        session,
        f"{ESAJ_BASE}cjpg/obterArquivo.do",
        {"cdProcesso": cd_processo, "cdForo": cd_foro, "nmAlias": nm_alias, "cdDocumento": cd_documento},
    )
    redirecionamentos[f"sentenca_{cd_documento}"] = local
    time.sleep(1.5)
    dump(dest / f"pasta_{cd_documento}.html", session.get(local, timeout=60).content)
    dump(dest / "redirecionamentos.json", json.dumps(redirecionamentos, indent=1).encode())
    logger.info("[tjsp] documentos: %s redirecionamentos em %s", len(redirecionamentos), dest)


# ---------- árvores de seleção (*TreeSelect.do) --------------------------

# Nós que o recorte mantém além dos primeiros de cada lista: o nó que
# tests/tjsp/test_arvore_contract.py confere em cada árvore e, em classes_2, a
# folha selecionável na raiz de test_arvore_granular.py. O eSAJ muda a ordem
# dos nós entre respostas, então os primeiros de cada lista não são estáveis.
ARVORE_NOS_EXTRAS: dict[str, tuple[str, ...]] = {arvore: (no,) for arvore, (no, _) in NO_ESPERADO.items()}
ARVORE_NOS_EXTRAS["classes_2"] += ("12227",)

# Itens mantidos em cada <ul> da árvore, além dos de ARVORE_NOS_EXTRAS.
ARVORE_ITENS_POR_LISTA = 2


def recortar_arvore(html: str, nos_extras: tuple[str, ...]) -> str:
    """Recorta a árvore: os primeiros ``<li>`` de cada ``<ul>``, mais os que levam a ``nos_extras``.

    Os nós mantidos saem com textos e atributos intactos; o HTML é
    reserializado pelo BeautifulSoup, e o espaço em branco entre as tags, que
    o JSP do eSAJ deixa aos montes, vira uma quebra de linha.
    """
    soup = BeautifulSoup(html, "html.parser")
    caminhos: set[int] = set()  # id() dos <li> que levam a um nó extra
    for no in nos_extras:
        alvo = soup.find("span", id=re.compile(rf"_tree_node_{re.escape(no)}$"))
        if alvo is None:
            raise ValueError(f"nó {no} ausente da árvore")
        caminhos.update(id(item) for item in alvo.find_parents("li"))
    for lista in soup.find_all("ul"):
        if lista.decomposed:
            continue
        for posicao, item in enumerate(lista.find_all("li", recursive=False)):
            if posicao >= ARVORE_ITENS_POR_LISTA and id(item) not in caminhos:
                item.decompose()
    # Depois do recorte, que deixa poucos nós de texto. Só espaço ASCII: o
    # &nbsp; (\xa0) dos <span class="ie"> fica.
    for texto in soup.find_all(string=True):
        if not texto.strip(" \t\r\n") and not isinstance(texto, Comment):
            texto.replace_with("\n")
    return str(soup)


def capture_arvores() -> None:
    """Grava ``arvore/<arvore>_min.html``: o recorte de cada árvore de ``TREE_ENDPOINTS`` do TJSP.

    Árvore que falha (erro HTTP, nó extra ausente) mantém o sample anterior;
    as outras seguem.
    """
    dest = samples_dir_for("tjsp", "arvore")
    session = build_session(headers=TJSP_CHROME_HEADERS)
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    for arvore, rota in jus.scraper("tjsp").TREE_ENDPOINTS.items():
        time.sleep(1.5)
        nos_extras = ARVORE_NOS_EXTRAS[arvore]
        try:
            resposta = session.get(f"{ESAJ_BASE}{rota}", timeout=120)
            resposta.raise_for_status()
            resposta.encoding = "utf-8"
            recorte = recortar_arvore(resposta.text, nos_extras)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("[tjsp] árvore %s FAILED: %s; sample mantido", arvore, exc)
            continue
        cabecalho = (
            f"<!-- Recorte da resposta real de {rota} do TJSP, capturada em\n"
            f"     {hoje} (UTF-8) e recortada por capture_arvores, em tests/fixtures/capture/tjsp.py:\n"
            f"     mantidos os {ARVORE_ITENS_POR_LISTA} primeiros <li> de cada <ul> e os que levam\n"
            f"     aos nós {', '.join(nos_extras)}. -->\n"
        )
        dump(dest / f"{arvore}_min.html", (cabecalho + recorte).encode("utf-8"))
        logger.info("[tjsp] árvore %s: %s → %s bytes", arvore, len(resposta.content), len(recorte.encode()))


# ---------- orchestrator -------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cnj", default=DEFAULT_CNJ, help="CNJ for cpopg/cposg captures")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        choices=[
            "cjsg", "cjpg", "cpopg_html", "cpopg_outros_assuntos", "cposg_html", "acordao", "documentos", "arvores",
        ],
        help="Flows to skip",
    )
    args = parser.parse_args()

    flows = [
        ("cjsg", lambda: capture_cjsg()),
        ("cjpg", lambda: capture_cjpg()),
        ("cpopg_html", lambda: capture_cpopg_html(args.cnj)),
        ("cpopg_outros_assuntos", capture_cpopg_outros_assuntos),
        ("cposg_html", lambda: capture_cposg_html(args.cnj)),
        ("acordao", capture_acordao),
        ("documentos", capture_documentos),
        ("arvores", capture_arvores),
    ]
    for name, fn in flows:
        if name in args.skip:
            logger.info("[tjsp] skipping %s", name)
            continue
        try:
            fn()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("[tjsp] %s FAILED: %s", name, exc)

    root: Path = samples_dir_for("tjsp", "cjsg").parent
    logger.info("[tjsp] done. See %s", root)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
