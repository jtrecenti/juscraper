"""HTTP layer for the TRF1 PJe public-process consultation.

A single ``cpopg`` lookup is three requests:

1. ``GET BASE_URL + ConsultaPublica/listView.seam`` — primes the session
   and returns the form HTML, from which the auto-generated JSF IDs
   (``j_idNNN``) are extracted at runtime.
2. ``POST <same URL>`` with the search payload — returns an Ajax fragment
   carrying a ``ca=<token>`` link when the process is found.
3. ``GET BASE_URL + ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam?ca=<token>``
   — returns the full process detail page (latin-1 encoded).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import requests

BASE_URL = "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"

# Browser-realistic header set. TRF1 has not surfaced an Akamai-style
# bot challenge so far, but sending the same Chrome-flavored headers as
# TRF3/TRF5 keeps the session-priming behavior predictable.
BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

LISTVIEW_PATH = "ConsultaPublica/listView.seam"
DETAIL_PATH = "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"

_CA_TOKEN_RE = re.compile(r"ca=([0-9a-f]+)")


@dataclass(frozen=True)
class FormFieldIds:
    """JSF auto-generated IDs needed to build a valid TRF1 search payload.

    The ``j_idNNN`` numbers vary per deployment but are stable across
    requests within a deployment; we re-extract them on every fresh session
    to absorb any redeploy without code changes.
    """

    processo_referencia: str  # ``fPP:j_idNNN:processoReferenciaInput``
    nome_advogado: str  # ``fPP:j_idNNN:nomeAdv``
    classe_judicial: str  # ``fPP:j_idNNN:classeJudicial`` (autocomplete)
    oab_decoration: str  # ``fPP:Decoration:j_idNNN`` (second OAB digit field)
    search_trigger: str  # ``fPP:j_idNNN`` — JSF Ajax behaviour bound to ``executarPesquisa()``


def extract_form_field_ids(form_html: str) -> FormFieldIds:
    """Pull the dynamic ``j_idNNN`` IDs out of TRF1's form HTML."""
    def _find(pattern: str, label: str) -> str:
        m = re.search(pattern, form_html)
        if not m:
            raise RuntimeError(f"TRF1: could not locate {label} field in form HTML")
        return m.group(1)

    processo_ref_id = _find(
        r'name="fPP:(j_id\d+):processoReferenciaInput"', "processoReferenciaInput"
    )
    nome_adv_id = _find(r'name="fPP:(j_id\d+):nomeAdv"', "nomeAdv")
    classe_id = _find(r'name="fPP:(j_id\d+):classeJudicial"', "classeJudicial")
    oab_deco_id = _find(r'name="fPP:Decoration:(j_id\d+)"', "Decoration:j_idNNN")

    # The search button's JSF Ajax behaviour is bound to a generated
    # ``<script id="fPP:j_idNNN">`` that defines ``executarPesquisa()``. The
    # backend expects ``fPP:j_idNNN=fPP:j_idNNN`` in the POST payload as the
    # event source — submitting the button name verbatim returns an empty
    # Ajax fragment.
    m = re.search(
        r"'parameters':\s*\{\s*'(fPP:j_id\d+)'\s*:\s*'fPP:j_id\d+'\s*\}",
        form_html,
    )
    if not m:
        raise RuntimeError(
            "TRF1: could not locate executarPesquisa search trigger in form HTML"
        )
    return FormFieldIds(
        processo_referencia=processo_ref_id,
        nome_advogado=nome_adv_id,
        classe_judicial=classe_id,
        oab_decoration=oab_deco_id,
        search_trigger=m.group(1),
    )


def build_search_payload(
    numero_processo: str,
    field_ids: FormFieldIds,
) -> dict[str, str]:
    """Build the ``application/x-www-form-urlencoded`` body for a CNJ lookup.

    All filter fields except the process number are submitted empty — that is
    how PJe's own JS submits when only the process number is filled, and the
    backend tolerates omitted optional fields only when the radio/select
    "control" fields are present alongside.

    TRF1 specifics (mirror TRF3):

    * ``classeJudicial`` is an autocomplete component (with paired
      ``sgbClasseJudicial_selection``).
    * ``dataAutuacaoDecoration`` is rendered, so the date inputs are part of
      the expected payload.
    """
    return {
        "AJAXREQUEST": "_viewRoot",
        "fPP:numProcesso-inputNumeroProcessoDecoration:numProcesso-inputNumeroProcesso": (
            numero_processo
        ),
        "mascaraProcessoReferenciaRadio": "on",
        f"fPP:{field_ids.processo_referencia}:processoReferenciaInput": "",
        "fPP:dnp:nomeParte": "",
        f"fPP:{field_ids.nome_advogado}:nomeAdv": "",
        f"fPP:{field_ids.classe_judicial}:classeJudicial": "",
        f"fPP:{field_ids.classe_judicial}:sgbClasseJudicial_selection": "",
        "tipoMascaraDocumento": "on",
        "fPP:dpDec:documentoParte": "",
        "fPP:Decoration:numeroOAB": "",
        f"fPP:Decoration:{field_ids.oab_decoration}": "",
        "fPP:Decoration:estadoComboOAB": (
            "org.jboss.seam.ui.NoSelectionConverter.noSelectionValue"
        ),
        "fPP:dataAutuacaoDecoration:dataAutuacaoInicioInputDate": "",
        "fPP:dataAutuacaoDecoration:dataAutuacaoFimInputDate": "",
        "fPP": "fPP",
        "autoScroll": "",
        "javax.faces.ViewState": "j_id1",
        # Trigger the Ajax behaviour bound to ``executarPesquisa()`` — the
        # generated ``j_idNNN`` is what the backend matches against the
        # form's UIComponent registry. The button id ``fPP:searchProcessos``
        # is decorative; submitting it instead returns an empty fragment.
        field_ids.search_trigger: field_ids.search_trigger,
        "AJAX:EVENTS_COUNT": "1",
    }


def extract_ca_token(search_html: str) -> Optional[str]:
    """Return the ``ca=<token>`` from a search response, or ``None`` if no result."""
    m = _CA_TOKEN_RE.search(search_html)
    return m.group(1) if m else None


def fetch_form(session: requests.Session, timeout: float = 30.0) -> str:
    """``GET`` the form page and return its UTF-8 text."""
    url = BASE_URL + LISTVIEW_PATH
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def submit_search(
    session: requests.Session,
    payload: dict[str, str],
    timeout: float = 30.0,
) -> str:
    """``POST`` the search payload and return the Ajax fragment text (UTF-8)."""
    url = BASE_URL + LISTVIEW_PATH
    resp = session.post(
        url,
        data=payload,
        timeout=timeout,
        headers={
            "Referer": url,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    resp.raise_for_status()
    return resp.text


def fetch_detail(
    session: requests.Session,
    ca_token: str,
    timeout: float = 30.0,
) -> str:
    """``GET`` the detail page and return its **latin-1** decoded text.

    The detail page is served without a charset declaration but contains
    bytes that are invalid UTF-8 (e.g. ``0xe7``); decoding as latin-1 is
    lossless for ISO-8859-1 / Windows-1252 content.
    """
    url = BASE_URL + DETAIL_PATH
    resp = session.get(
        url,
        params={"ca": ca_token},
        timeout=timeout,
        headers={"Referer": BASE_URL + LISTVIEW_PATH},
    )
    resp.raise_for_status()
    return resp.content.decode("latin-1")


# ---------------------------------------------------------------------------
# Movimentações pagination
# ---------------------------------------------------------------------------
#
# PJe renders the movimentações table as a 15-row dataTable paged by a
# Richfaces 3 inslider widget. The first page comes embedded in the detail
# HTML; pages 2..N are fetched by POSTing the slider form back to
# ``listView.seam`` with ``AJAXREQUEST=<containerId>``. The auto-generated
# ``j_idNNN`` IDs needed for the POST are extracted from the slider's
# ``onchange`` script in the detail HTML.

# Stable landmark IDs that bracket the movs panel in the detail HTML —
# we search for the slider script *between* these to avoid picking up the
# documentos table's slider, which has the same component class.
_MOVS_PANEL_MARKER = "processoEventoPanel"
_DOCS_PANEL_MARKER = "processoDocumentoGridTabPanel"

_VIEW_STATE_RE = re.compile(
    r'name="javax\.faces\.ViewState"\s+id="javax\.faces\.ViewState"\s+value="([^"]+)"'
)


@dataclass(frozen=True)
class MovsPagination:
    """Coordinates needed to POST the movimentações paginator back to PJe."""

    form_id: str  # e.g. ``j_id149:j_id560``
    slider_input_name: str  # e.g. ``j_id149:j_id560:j_id561`` (carries page value)
    ajax_source_name: str  # e.g. ``j_id149:j_id560:j_id562`` (slider listener)
    container_id: str  # e.g. ``j_id149:j_id477`` (panel updated on AJAX)
    max_pages: int
    view_state: str  # e.g. ``j_id2``


def extract_movs_pagination(detail_html: str) -> Optional[MovsPagination]:
    """Locate the Richfaces slider that paginates the movs table.

    Returns ``None`` when the process has 15 or fewer movimentações (PJe omits
    the slider in that case), so the caller can skip the extra round-trips.
    """
    panel_idx = detail_html.find(_MOVS_PANEL_MARKER)
    if panel_idx == -1:
        return None
    end_idx = detail_html.find(_DOCS_PANEL_MARKER, panel_idx)
    if end_idx == -1:
        end_idx = len(detail_html)
    region = detail_html[panel_idx:end_idx]
    # The slider call has nested parens (the embedded ``A4J.AJAX.Submit(...)``
    # JS string), so we anchor on a wide trailing window instead of trying to
    # balance brackets.
    sl_start = region.find("new Richfaces.Slider")
    if sl_start == -1:
        return None
    block = region[sl_start : sl_start + 2500]
    sl = re.match(r'new Richfaces\.Slider\("([^"]+)"', block)
    if not sl:
        return None
    slider_id = sl.group(1)  # ``<form_id>:<slider_id>``
    max_match = re.search(r"'maxValue':'(\d+)'", block)
    if not max_match:
        return None
    # Inside the ``onchange`` JS string, single quotes are escaped as ``\'``.
    # Inside the ``onchange`` JS string every quote is escaped as ``\'``,
    # so the keys read ``\'similarityGroupingId\'`` etc. We anchor on the key
    # name and let the surrounding ``\'`` floats absorb the escapes.
    sim_match = re.search(r"similarityGroupingId\\':\\'([^']+)\\'", block)
    cont_match = re.search(r"containerId\\':\\'([^']+)\\'", block)
    if not (sim_match and cont_match):
        return None
    vs_match = _VIEW_STATE_RE.search(detail_html)
    if not vs_match:
        return None
    form_id = ":".join(slider_id.split(":")[:-1])
    return MovsPagination(
        form_id=form_id,
        slider_input_name=slider_id,
        ajax_source_name=sim_match.group(1),
        container_id=cont_match.group(1),
        max_pages=int(max_match.group(1)),
        view_state=vs_match.group(1),
    )


def fetch_movs_page(
    session: requests.Session,
    info: MovsPagination,
    page: int,
    ca_token: str,
    timeout: float = 30.0,
) -> str:
    """Fetch a single movs page (>=2) as the latin-1 AJAX fragment.

    Page 1 already comes in the detail HTML; pages 2..``info.max_pages`` are
    fetched by reproducing the Richfaces inslider POST. The trick is that
    ``AJAXREQUEST`` carries the *container id* (the panel to refresh), not the
    usual ``_viewRoot`` value used by initial form submits.
    """
    url = BASE_URL + DETAIL_PATH
    data = {
        "AJAXREQUEST": info.container_id,
        info.slider_input_name: str(page),
        info.form_id: info.form_id,
        "autoScroll": "",
        "javax.faces.ViewState": info.view_state,
        info.ajax_source_name: info.ajax_source_name,
        "AJAX:EVENTS_COUNT": "1",
    }
    resp = session.post(
        url,
        data=data,
        timeout=timeout,
        headers={
            "Referer": f"{url}?ca={ca_token}",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
    )
    resp.raise_for_status()
    return resp.content.decode("latin-1")


_TBODY_OPEN_RE = re.compile(
    r'(<tbody[^>]*\bid="[^"]*:processoEvento:tb"[^>]*>)', re.IGNORECASE
)
_TBODY_CLOSE = "</tbody>"


def _extract_movs_rows(fragment_html: str) -> str:
    """Return the inner HTML of the ``processoEvento:tb`` tbody (rows only)."""
    m = _TBODY_OPEN_RE.search(fragment_html)
    if not m:
        return ""
    start = m.end()
    end = fragment_html.find(_TBODY_CLOSE, start)
    if end == -1:
        return ""
    return fragment_html[start:end]


def merge_movs_pages(detail_html: str, extra_pages: list[str]) -> str:
    """Splice rows from pages 2..N into page 1's ``processoEvento`` tbody.

    Returns ``detail_html`` unchanged when there is nothing to merge or the
    tbody marker can't be located. Duplicate row IDs across pages are
    intentional — the parser keys off cell content, not row IDs.
    """
    if not extra_pages:
        return detail_html
    m = _TBODY_OPEN_RE.search(detail_html)
    if not m:
        return detail_html
    end = detail_html.find(_TBODY_CLOSE, m.end())
    if end == -1:
        return detail_html
    appended = "".join(_extract_movs_rows(p) for p in extra_pages)
    return detail_html[:end] + appended + detail_html[end:]
