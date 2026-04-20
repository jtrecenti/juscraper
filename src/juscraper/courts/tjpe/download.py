"""
Downloads raw results from the TJPE jurisprudence search.

The TJPE website is a stateful JSF/RichFaces application.  The search flow is:

1. GET  consulta.xhtml          -> obtain JSESSIONID + ViewState
2. POST consulta.xhtml          -> results page (single type) or "escolha" page (multiple types)
3. (if escolha) POST escolhaResultado.xhtml -> results page 1
4. AJAX POST resultado.xhtml    -> paginate to page N
"""

import logging
import math
import re
import time

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tjpe.jus.br/consultajurisprudenciaweb/xhtml/consulta"

RESULTS_PER_PAGE = 5


def _extract_viewstate(html: str) -> str:
    """Extract javax.faces.ViewState from the HTML."""
    match = re.search(
        r'name="javax\.faces\.ViewState"[^>]*value="([^"]*)"', html
    )
    if not match:
        raise ValueError("Could not find javax.faces.ViewState in response")
    return match.group(1)


def _extract_total_docs(html: str) -> int:
    """Extract total document count from the results page.

    Handles two formats:
    - Results page: "Documentos encontrados: </label>...<span>996</span>"
    - Escolha page: "953 documentos encontrados"
    """
    # Format 1: results page with <span>
    match = re.search(
        r"Documentos encontrados:.*?<span>(\d+)</span>", html, re.DOTALL
    )
    if match:
        return int(match.group(1))

    # Format 2: escolha page
    match = re.search(r"(\d+)\s+documentos encontrados", html)
    if match:
        return int(match.group(1))

    return 0


def _is_results_page(html: str) -> bool:
    """Check if the HTML is a results page (not the escolha page)."""
    return "Documentos encontrados:" in html and "Documento 1" in html


def _is_escolha_page(html: str) -> bool:
    """Check if we got the 'escolha' page (choose result type)."""
    return "documentos encontrados" in html and "Documento 1" not in html


def _extract_escolha_button_id(html: str, tipo: str = "Acórdãos") -> str:
    """Extract the form submit ID for the result type link on the escolha page."""
    soup = BeautifulSoup(html, "lxml")
    for link in soup.find_all("a", onclick=True):
        if "documentos encontrados" in link.get_text():
            td = link.find_parent("td")
            if td:
                row = td.find_parent("tr")
                if row:
                    label_cell = row.find("td")
                    label_el = label_cell.find("label") if label_cell else None
                    label_text = label_el.get_text(strip=True) if label_el else ""
                    if label_text == tipo:
                        onclick = str(link["onclick"])
                        match = re.search(r"'([^']+)':'[^']+'", onclick)
                        if match:
                            return match.group(1)
    raise ValueError(f"Could not find escolha button for '{tipo}'")


def _extract_pagination_ids(html: str):
    """Extract the form ID and datascroller ID for AJAX pagination."""
    # The datascroller ID reveals the form ID (e.g. "j_id81:j_id87")
    scroller_match = re.search(
        r'class="rich-datascr[^"]*"\s+id="([^"]+)"', html
    )
    if scroller_match:
        scroller_id = scroller_match.group(1)
        form_id = scroller_id.split(":")[0]
    else:
        # Fallback: find the form with class form-consulta
        form_match = re.search(
            r'<form id="([^"]+)"[^>]*class="form-consulta"', html
        )
        form_id = form_match.group(1) if form_match else "j_id81"
        scroller_id = f"{form_id}:j_id87"

    return form_id, scroller_id


def _step1_get_session(session: requests.Session) -> tuple[str, str]:
    """GET the search page; return (HTML, ViewState)."""
    url = f"{BASE_URL}/consulta.xhtml"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text, _extract_viewstate(resp.text)


def _step2_post_search(
    session: requests.Session,
    viewstate: str,
    pesquisa: str,
    data_julgamento_inicio: Optional[str] = None,
    data_julgamento_fim: Optional[str] = None,
    relator: Optional[str] = None,
    classe_cnj: Optional[str] = None,
    assunto_cnj: Optional[str] = None,
    meio_tramitacao: Optional[str] = None,
    tipo_decisao: str = "acordaos",
    search_html: Optional[str] = None,
) -> tuple[str, str]:
    """POST the search form; return (response HTML, ViewState).

    The response is either the results page directly (single type)
    or the escolha page (multiple types).
    """
    url = f"{BASE_URL}/consulta.xhtml"

    # Try to extract submit button ID from search page
    submit_id = "formPesquisaJurisprudencia:j_id101"
    if search_html:
        match = re.search(
            r"jsfcljs\([^)]+\{'(formPesquisaJurisprudencia:[^']+)'"
            r"[^)]*\)[^>]*>Pesquisar",
            search_html,
        )
        if match:
            submit_id = match.group(1)

    # Build type checkboxes
    tipo_acordao = "on" if tipo_decisao in ("acordaos", "todos") else ""
    tipo_monocratica = "on" if tipo_decisao in ("monocraticas", "todos") else ""
    tipo_todos = "on" if tipo_decisao == "todos" else ""

    data = {
        "formPesquisaJurisprudencia": "formPesquisaJurisprudencia",
        "formPesquisaJurisprudencia:inputBuscaSimples": pesquisa or "",
        "tipo_processo": "NPU",
        "formPesquisaJurisprudencia:j_id46": "",
        "formPesquisaJurisprudencia:j_id48": "",
        "formPesquisaJurisprudencia:numeroAntigoDigito": "",
        "formPesquisaJurisprudencia:numeroAntigoBarramento": "",
        "formPesquisaJurisprudencia:j_id59InputDate": data_julgamento_inicio or "",
        "formPesquisaJurisprudencia:j_id59InputCurrentDate": "04/2026",
        "formPesquisaJurisprudencia:periodoFimInputDate": data_julgamento_fim or "",
        "formPesquisaJurisprudencia:periodoFimInputCurrentDate": "04/2026",
        "formPesquisaJurisprudencia:selectRelator": relator or "",
        "formPesquisaJurisprudencia:selectClasseCNJ": classe_cnj or "",
        "formPesquisaJurisprudencia:selectAssuntoCNJ": assunto_cnj or "",
        "formPesquisaJurisprudencia:selectMeioTramitacao": meio_tramitacao or "",
        "javax.faces.ViewState": viewstate,
        submit_id: submit_id,
    }
    if tipo_acordao:
        data["formPesquisaJurisprudencia:tipoAcordao"] = tipo_acordao
    if tipo_monocratica:
        data["formPesquisaJurisprudencia:tipoDecisaoMonocratica"] = tipo_monocratica
    if tipo_todos:
        data["formPesquisaJurisprudencia:tipoTodos"] = tipo_todos

    resp = session.post(url, data=data, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text, _extract_viewstate(resp.text)


def _step3_choose_tipo(
    session: requests.Session,
    viewstate: str,
    escolha_html: str,
    tipo: str = "Acórdãos",
) -> tuple[str, str]:
    """POST to choose Acordaos or Decisoes Monocraticas; return (results HTML, ViewState)."""
    url = f"{BASE_URL}/escolhaResultado.xhtml"
    button_id = _extract_escolha_button_id(escolha_html, tipo)

    data = {
        "resultadoForm": "resultadoForm",
        "javax.faces.ViewState": viewstate,
        button_id: button_id,
    }
    resp = session.post(url, data=data, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text, _extract_viewstate(resp.text)


def _step4_paginate(
    session: requests.Session,
    viewstate: str,
    form_id: str,
    scroller_id: str,
    pesquisa: str,
    page_number: int,
) -> str:
    """AJAX POST to fetch a specific page; return HTML."""
    url = f"{BASE_URL}/resultado.xhtml"

    data = {
        "AJAXREQUEST": "_viewRoot",
        form_id: form_id,
        "hiddenPesquisaLivre": pesquisa or "",
        "javax.faces.ViewState": viewstate,
        scroller_id: str(page_number),
        "AJAX:EVENTS_COUNT": "1",
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    resp = session.post(url, data=data, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def cjsg_download(
    pesquisa: str,
    paginas=None,
    data_julgamento_inicio: Optional[str] = None,
    data_julgamento_fim: Optional[str] = None,
    relator: Optional[str] = None,
    classe_cnj: Optional[str] = None,
    assunto_cnj: Optional[str] = None,
    meio_tramitacao: Optional[str] = None,
    tipo_decisao: str = "acordaos",
    session: Optional[requests.Session] = None,
) -> list[str]:
    """
    Download raw HTML pages from the TJPE jurisprudence search.

    Returns a list of HTML strings, one per page.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    tipo_label = {
        "acordaos": "Acórdãos",
        "monocraticas": "Decisões Monocráticas",
    }.get(tipo_decisao, "Acórdãos")

    # Step 1 - GET search page
    search_html, vs = _step1_get_session(session)
    time.sleep(1)

    # Step 2 - POST search form
    response_html, vs = _step2_post_search(
        session, vs, pesquisa,
        data_julgamento_inicio=data_julgamento_inicio,
        data_julgamento_fim=data_julgamento_fim,
        relator=relator,
        classe_cnj=classe_cnj,
        assunto_cnj=assunto_cnj,
        meio_tramitacao=meio_tramitacao,
        tipo_decisao=tipo_decisao,
        search_html=search_html,
    )
    time.sleep(1)

    # Step 2 may return results directly (single type) or escolha page (multiple types)
    if _is_escolha_page(response_html):
        # Step 3 - choose result type
        results_html, vs = _step3_choose_tipo(session, vs, response_html, tipo_label)
        time.sleep(1)
    elif _is_results_page(response_html):
        results_html = response_html
    else:
        logger.warning("TJPE: unexpected response after search")
        return []

    total_docs = _extract_total_docs(results_html)
    if total_docs == 0:
        logger.info("TJPE: no documents found for '%s'", pesquisa)
        return []

    total_pages = math.ceil(total_docs / RESULTS_PER_PAGE)
    logger.info("TJPE: %d documents found (%d pages)", total_docs, total_pages)

    form_id, scroller_id = _extract_pagination_ids(results_html)

    # Determine pages to download
    pages_iter: list = (
        list(range(1, total_pages + 1)) if paginas is None else list(paginas)
    )

    results = []

    for page_num in tqdm(pages_iter, desc=f"Downloading TJPE {tipo_label}"):
        if page_num == 1:
            results.append(results_html)
        else:
            html = _step4_paginate(session, vs, form_id, scroller_id, pesquisa, page_num)
            results.append(html)
            time.sleep(1)

    return results
