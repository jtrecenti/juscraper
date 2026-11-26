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
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from juscraper.courts._esaj.acordao import paginas_movimentacoes

from ._util import (
    TJSP_CHROME_HEADERS,
    build_session,
    capture_acordao_samples,
    capture_cjsg_samples,
    dump,
    fetch_cjsg_pages,
    make_tjsp_cjpg_params,
    make_tjsp_cjsg_body,
    samples_dir_for,
)

ESAJ_BASE = "https://esaj.tjsp.jus.br/"

# CNJ used by the existing integration tests (tests/tjsp/test_cpopg.py).
# If it disappears from the TJSP index, pass --cnj to override.
DEFAULT_CNJ = "1000149-71.2024.8.26.0346"

# Número sem processo no TJSP, para a busca "Não existem informações disponíveis".
CPOPG_CNJ_INEXISTENTE = "0000001-12.2024.8.26.0100"


def _clean_cnj(cnj: str) -> str:
    """Strip non-digit characters from a CNJ. Mirrors ``utils.cnj.clean_cnj``."""
    return re.sub(r"[^0-9]", "", cnj)


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
        print("[tjsp] cjsg ementa_com_resultados: a 1a página mudou; sample mantido")
    else:
        dump(samples_dir_for("tjsp", "cjsg") / "ementa_com_resultados.html", resps[0].content)
        print("[tjsp] cjsg ementa_com_resultados ('direito', baixar_sg=False) → saved")
    capture_cjsg_sem_ementa()


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
        print(f"[tjsp] cjsg sem_ementa: {com_ementa} de {len(linhas)} linhas com ementa; sample mantido")
        return
    dump(samples_dir_for("tjsp", "cjsg") / "sem_ementa.html", resps[0].content)
    print(f"[tjsp] cjsg sem_ementa: {len(linhas) - com_ementa} de {len(linhas)} linhas sem ementa → saved")


# ---------- cjpg ---------------------------------------------------------

def _fetch_cjpg_page1(session: requests.Session, pesquisa: str) -> requests.Response:
    # Warm the session on the cjpg home page so the server sets the JSESSIONID
    # and any CSRF cookies; then submit the query. The scraper itself doesn't
    # do this, but live browsers do — the eSAJ cjpg backend increasingly
    # refuses anonymous queries without a prior cookie-setting hit.
    session.get(f"{ESAJ_BASE}cjpg/open.do", timeout=60)
    params = make_tjsp_cjpg_params(pesquisa)
    r = session.get(f"{ESAJ_BASE}cjpg/pesquisar.do", params=params, timeout=60)
    r.raise_for_status()
    return r


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
    resposta = _fetch_cjpg_page1(session, "jurimétrica")
    linhas = BeautifulSoup(resposta.content, "html.parser").select("#divDadosResultado tr.fundocinza1")
    if not 0 < len(linhas) < 10:
        # Com 10 linhas pode haver página 2, e o sample deixaria de exercitar o caso.
        print(f"[tjsp] cjpg single_page: {len(linhas)} linhas na 1a página; sample mantido")
        return
    dump(samples_dir_for("tjsp", "cjpg") / "single_page.html", resposta.content)
    print(f"[tjsp] cjpg single_page ('jurimétrica', {len(linhas)} resultado(s)) → saved")


def capture_cjpg_sentenca_sem_bens() -> None:
    """Grava ``cjpg/sentenca_nao_foram_encontrados.html``: sentenças que citam "não foram encontrados".

    A frase é um dos marcadores de busca sem resultado. Em 26/11/2026, a busca
    trouxe "Resultados 1 a 10 de 102853", e a contagem dava 0 porque lia o
    texto das sentenças.
    """
    session = build_session(headers=TJSP_CHROME_HEADERS)
    resposta = _fetch_cjpg_page1(session, '"não foram encontrados bens"')
    if "não foram encontrados" not in resposta.text:
        # Sem a frase, o sample deixaria de exercitar o caso.
        print("[tjsp] cjpg sentenca_nao_foram_encontrados: frase ausente na 1a página; sample mantido")
        return
    dump(samples_dir_for("tjsp", "cjpg") / "sentenca_nao_foram_encontrados.html", resposta.content)
    print("[tjsp] cjpg sentenca_nao_foram_encontrados → saved")


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
        r1 = _fetch_cjpg_page1(session, "dano moral")
        dump(dest / "results_normal_page_01.html", r1.content)
        time.sleep(1.5)
        r2 = _fetch_cjpg_page_n(session, 2)
        dump(dest / "results_normal_page_02.html", r2.content)
        print("[tjsp] cjpg typical ('dano moral') → 2 pages saved")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[tjsp] cjpg typical FAILED: {exc}")

    try:
        capture_cjpg_single_page()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[tjsp] cjpg single_page FAILED: {exc}")

    try:
        capture_cjpg_sentenca_sem_bens()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[tjsp] cjpg sentenca_nao_foram_encontrados FAILED: {exc}")

    try:
        session = build_session(headers=TJSP_CHROME_HEADERS)
        r_none = _fetch_cjpg_page1(session, "juscraper_probe_zero_hits_xyzqwe")
        dump(dest / "no_results.html", r_none.content)
        print("[tjsp] cjpg no_results → saved")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[tjsp] cjpg no_results FAILED: {exc}")


# ---------- cpopg html ---------------------------------------------------

def capture_cpopg_html(cnj: str) -> None:
    """Capture cpopg samples for ``method='html'``.

    Fetches ``search.do`` for ``cnj`` and one ``show.do`` per link returned.
    Overwrites ``show_standard.html`` — legacy synthetic samples live in the
    same directory under their kept names (``show_standard.html``,
    ``show_alternative.html``) and remain for unit tests.
    """
    dest = samples_dir_for("tjsp", "cpopg")
    session = build_session(headers=TJSP_CHROME_HEADERS)

    # search
    id_clean = _clean_cnj(cnj)
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
    print(f"[tjsp] cpopg html search for {cnj} → saved")

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
    print(f"[tjsp] cpopg html search for {CPOPG_CNJ_INEXISTENTE} → saved")

    # parse the search response to discover the processo.codigo param
    # (simplified: regex over the HTML; scraper uses BeautifulSoup but we
    # just need the codes for sample capture)
    codigos = re.findall(r"processo\.codigo=([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        print(f"[tjsp] cpopg html: no processo.codigo in search response for {cnj}")
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
    print(f"[tjsp] cpopg html show for codigo={cd} → saved")
    _ = id_clean  # referenced for symmetry with scraper internals


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
    print("[tjsp] cposg html open → saved")

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
    print(f"[tjsp] cposg html search for {cnj} → saved")

    codigos = re.findall(r"processo\.codigo=([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        # Try alternative selector for the "simple" response variant
        codigos = re.findall(r"cdProcesso[\"']\s+value=[\"']([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        print(f"[tjsp] cposg html: no process code found in search response for {cnj}")
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
            print(f"[tjsp] cposg html movimentações página {numero} → saved")

    cd = codigos[0]
    r_show = session.get(
        f"{ESAJ_BASE}cposg/show.do",
        params={"processo.codigo": cd},
        timeout=60,
    )
    r_show.raise_for_status()
    dump(dest / "show.html", r_show.content)
    print(f"[tjsp] cposg html show for codigo={cd} → saved")


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
    print("[tjsp] acordao: verificarAcesso sem movimentações carregadas → saved")


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
    print(f"[tjsp] documentos: {len(redirecionamentos)} redirecionamentos em {dest}")


# ---------- orchestrator -------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cnj", default=DEFAULT_CNJ, help="CNJ for cpopg/cposg captures")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        choices=["cjsg", "cjpg", "cpopg_html", "cposg_html", "acordao", "documentos"],
        help="Flows to skip",
    )
    args = parser.parse_args()

    flows = [
        ("cjsg", lambda: capture_cjsg()),
        ("cjpg", lambda: capture_cjpg()),
        ("cpopg_html", lambda: capture_cpopg_html(args.cnj)),
        ("cposg_html", lambda: capture_cposg_html(args.cnj)),
        ("acordao", capture_acordao),
        ("documentos", capture_documentos),
    ]
    for name, fn in flows:
        if name in args.skip:
            print(f"[tjsp] skipping {name}")
            continue
        try:
            fn()
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[tjsp] {name} FAILED: {exc}")

    root: Path = samples_dir_for("tjsp", "cjsg").parent
    print(f"[tjsp] done. See {root}")


if __name__ == "__main__":
    main()
