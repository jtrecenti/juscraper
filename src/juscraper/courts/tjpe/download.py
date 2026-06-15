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

from bs4 import BeautifulSoup
from tqdm import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import extract_count_with_cascade

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tjpe.jus.br/consultajurisprudenciaweb/xhtml/consulta"

CONSULTA_URL = f"{BASE_URL}/consulta.xhtml"
ESCOLHA_URL = f"{BASE_URL}/escolhaResultado.xhtml"
RESULTADO_URL = f"{BASE_URL}/resultado.xhtml"

RESULTS_PER_PAGE = 5

# Hint do calendario RichFaces (mes/ano corrente exibido pelo widget). O
# backend nao filtra por esses campos — sao echo do estado UI. Congelados
# para permitir matching byte-a-byte nos contratos offline.
_CURRENT_DATE_HINT = "04/2026"

# Submit button ID padrao quando o regex de extracao nao casa em `search_html`.
# O ID real vem do JS `jsfcljs(...)` na pagina de consulta.
DEFAULT_SUBMIT_ID = "formPesquisaJurisprudencia:j_id101"

_PAGINATION_CSS_SELECTORS: tuple[str, ...] = (
    "div.resultado-header table.table-header-resultado",
)
_PAGINATION_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"Documentos\s+encontrados:\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s+documentos\s+encontrados", re.IGNORECASE),
)
_ZERO_MARKERS: tuple[str, ...] = ("nenhum documento encontrado",)


def extract_viewstate(html: str) -> str:
    """Extract javax.faces.ViewState from the HTML."""
    match = re.search(
        r'name="javax\.faces\.ViewState"[^>]*value="([^"]*)"', html
    )
    if not match:
        raise ValueError("Could not find javax.faces.ViewState in response")
    return match.group(1)


def extract_total_docs(html: str) -> int:
    """Extract total document count using cascading selectors + regexes (refs #87)."""
    n = extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
        zero_markers=_ZERO_MARKERS,
        fallback_max_int=False,
    )
    return n if n is not None else 0


def is_results_page(html: str) -> bool:
    """Check if the HTML is a results page (not the escolha page).

    Case-insensitive: a results page traz o rotulo ``Documentos encontrados:``
    (com dois pontos — distingue da escolha) e o cabecalho ``Documento 1``.
    """
    html_lower = html.lower()
    return "documentos encontrados:" in html_lower and "documento 1" in html_lower


def is_escolha_page(html: str) -> bool:
    """Check if we got the 'escolha' page (choose result type).

    Case-insensitive: a pagina de escolha traz ``N documentos encontrados``
    (sem dois pontos) e nao tem o cabecalho ``Documento 1`` da pagina de
    resultados.
    """
    html_lower = html.lower()
    return "documentos encontrados" in html_lower and "documento 1" not in html_lower


def extract_escolha_button_id(html: str, tipo: str = "Acórdãos") -> str:
    """Extract the form submit ID for the result type link on the escolha page."""
    soup = BeautifulSoup(html, "html.parser")
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


def extract_pagination_ids(html: str) -> tuple[str, str]:
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


def extract_submit_id(search_html: str | None) -> str:
    """Extract the form submit button ID from the consulta.xhtml HTML.

    The ID comes from a ``jsfcljs(..., {'<form>:<id>':'...'}...)>Pesquisar``
    JavaScript call. Falls back to :data:`DEFAULT_SUBMIT_ID` quando o regex
    nao casa (defensivo — historicamente estavel).
    """
    if not search_html:
        return DEFAULT_SUBMIT_ID
    match = re.search(
        r"jsfcljs\([^)]+\{'(formPesquisaJurisprudencia:[^']+)'"
        r"[^)]*\)[^>]*>Pesquisar",
        search_html,
    )
    return match.group(1) if match else DEFAULT_SUBMIT_ID


def build_cjsg_form_body(
    viewstate: str,
    submit_id: str,
    pesquisa: str | None,
    *,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    relator: str | None = None,
    classe: str | None = None,
    assunto: str | None = None,
    meio_tramitacao: str | None = None,
    tipo_decisao: str = "acordaos",
    current_date_hint: str = _CURRENT_DATE_HINT,
) -> dict[str, str]:
    """Build the form-encoded body for the TJPE CJSG search ``POST consulta.xhtml``.

    Inclui apenas os campos que o JSF/RichFaces aceita; os tres checkboxes
    de tipo (``tipoAcordao`` / ``tipoDecisaoMonocratica`` / ``tipoTodos``)
    so aparecem quando ativos (ausencia difere de string vazia para o
    backend). Todos os valores sao retornados como strings para que
    :func:`responses.matchers.urlencoded_params_matcher` possa ser usado
    com ``allow_blank=True`` nos contratos. ``None`` em qualquer filtro
    opcional e tratado como string vazia (sem filtro).
    """
    body: dict[str, str] = {
        "formPesquisaJurisprudencia": "formPesquisaJurisprudencia",
        "formPesquisaJurisprudencia:inputBuscaSimples": pesquisa or "",
        "tipo_processo": "NPU",
        "formPesquisaJurisprudencia:j_id46": "",
        "formPesquisaJurisprudencia:j_id48": "",
        "formPesquisaJurisprudencia:numeroAntigoDigito": "",
        "formPesquisaJurisprudencia:numeroAntigoBarramento": "",
        "formPesquisaJurisprudencia:j_id59InputDate": data_julgamento_inicio or "",
        "formPesquisaJurisprudencia:j_id59InputCurrentDate": current_date_hint,
        "formPesquisaJurisprudencia:periodoFimInputDate": data_julgamento_fim or "",
        "formPesquisaJurisprudencia:periodoFimInputCurrentDate": current_date_hint,
        "formPesquisaJurisprudencia:selectRelator": relator or "",
        "formPesquisaJurisprudencia:selectClasseCNJ": classe or "",
        "formPesquisaJurisprudencia:selectAssuntoCNJ": assunto or "",
        "formPesquisaJurisprudencia:selectMeioTramitacao": meio_tramitacao or "",
        "javax.faces.ViewState": viewstate,
        submit_id: submit_id,
    }
    if tipo_decisao in ("acordaos", "todos"):
        body["formPesquisaJurisprudencia:tipoAcordao"] = "on"
    if tipo_decisao in ("monocraticas", "todos"):
        body["formPesquisaJurisprudencia:tipoDecisaoMonocratica"] = "on"
    if tipo_decisao == "todos":
        body["formPesquisaJurisprudencia:tipoTodos"] = "on"
    return body


def step1_get_session(request_fn: RequestFn) -> tuple[str, str]:
    """GET the search page; return (HTML, ViewState)."""
    resp = request_fn("GET", CONSULTA_URL, timeout=30)
    resp.encoding = resp.apparent_encoding
    return resp.text, extract_viewstate(resp.text)


def step2_post_search(
    request_fn: RequestFn,
    viewstate: str,
    pesquisa: str,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    relator: str | None = None,
    classe: str | None = None,
    assunto: str | None = None,
    meio_tramitacao: str | None = None,
    tipo_decisao: str = "acordaos",
    search_html: str | None = None,
) -> tuple[str, str]:
    """POST the search form; return (response HTML, ViewState).

    The response is either the results page directly (single type)
    or the escolha page (multiple types).
    """
    submit_id = extract_submit_id(search_html)
    data = build_cjsg_form_body(
        viewstate=viewstate,
        submit_id=submit_id,
        pesquisa=pesquisa,
        data_julgamento_inicio=data_julgamento_inicio,
        data_julgamento_fim=data_julgamento_fim,
        relator=relator,
        classe=classe,
        assunto=assunto,
        meio_tramitacao=meio_tramitacao,
        tipo_decisao=tipo_decisao,
    )
    resp = request_fn("POST", CONSULTA_URL, data=data, timeout=30)
    resp.encoding = resp.apparent_encoding
    return resp.text, extract_viewstate(resp.text)


def step3_choose_tipo(
    request_fn: RequestFn,
    viewstate: str,
    escolha_html: str,
    tipo: str = "Acórdãos",
) -> tuple[str, str]:
    """POST to choose Acordaos or Decisoes Monocraticas; return (results HTML, ViewState)."""
    button_id = extract_escolha_button_id(escolha_html, tipo)

    data = {
        "resultadoForm": "resultadoForm",
        "javax.faces.ViewState": viewstate,
        button_id: button_id,
    }
    resp = request_fn("POST", ESCOLHA_URL, data=data, timeout=30)
    resp.encoding = resp.apparent_encoding
    return resp.text, extract_viewstate(resp.text)


def step4_paginate(
    request_fn: RequestFn,
    viewstate: str,
    form_id: str,
    scroller_id: str,
    pesquisa: str,
    page_number: int,
) -> str:
    """AJAX POST to fetch a specific page; return HTML."""
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
    resp = request_fn("POST", RESULTADO_URL, data=data, headers=headers, timeout=30)
    resp.encoding = resp.apparent_encoding
    return resp.text


def cjsg_download(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    relator: str | None = None,
    classe: str | None = None,
    assunto: str | None = None,
    meio_tramitacao: str | None = None,
    tipo_decisao: str = "acordaos",
) -> list[str]:
    """
    Download raw HTML pages from the TJPE jurisprudence search.

    Args:
        request_fn: HTTP callable que aplica retry + ``raise_for_status``.
            Em uso normal e ``TJPEScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``).

    Returns a list of HTML strings, one per page.
    """
    tipo_label = {
        "acordaos": "Acórdãos",
        "monocraticas": "Decisões Monocráticas",
    }.get(tipo_decisao, "Acórdãos")

    # Step 1 - GET search page
    search_html, vs = step1_get_session(request_fn)
    time.sleep(1)

    # Step 2 - POST search form
    response_html, vs = step2_post_search(
        request_fn, vs, pesquisa,
        data_julgamento_inicio=data_julgamento_inicio,
        data_julgamento_fim=data_julgamento_fim,
        relator=relator,
        classe=classe,
        assunto=assunto,
        meio_tramitacao=meio_tramitacao,
        tipo_decisao=tipo_decisao,
        search_html=search_html,
    )
    time.sleep(1)

    # Step 2 may return results directly (single type) or escolha page (multiple types)
    if is_escolha_page(response_html):
        # Step 3 - choose result type
        results_html, vs = step3_choose_tipo(request_fn, vs, response_html, tipo_label)
        time.sleep(1)
    elif is_results_page(response_html):
        results_html = response_html
    else:
        logger.warning("TJPE: unexpected response after search")
        return []

    total_docs = extract_total_docs(results_html)
    if total_docs == 0:
        logger.info("TJPE: no documents found for '%s'", pesquisa)
        return []

    total_pages = math.ceil(total_docs / RESULTS_PER_PAGE)
    logger.info("TJPE: %d documents found (%d pages)", total_docs, total_pages)

    form_id, scroller_id = extract_pagination_ids(results_html)

    # Determine pages to download
    pages_iter: list = (
        list(range(1, total_pages + 1)) if paginas is None else list(paginas)
    )

    results = []

    for page_num in tqdm(pages_iter, desc=f"Downloading TJPE {tipo_label}"):
        if page_num == 1:
            results.append(results_html)
        else:
            html = step4_paginate(request_fn, vs, form_id, scroller_id, pesquisa, page_num)
            results.append(html)
            time.sleep(1)

    return results
