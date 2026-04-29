"""HTTP layer for the TRF3 PJe public-process consultation.

A single ``cpopg`` lookup is three requests:

1. ``GET BASE_URL + ConsultaPublica/listView.seam`` — primes the session
   (Akamai bot-challenge cookies — TRF3 sits behind ``ak_bmsc``) and returns
   the form HTML, from which the auto-generated JSF IDs (``j_idNNN``) are
   extracted at runtime.
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

BASE_URL = "https://pje1g.trf3.jus.br/pje/"

# Browser-realistic header set — TRF3 sits behind Akamai bot manager
# (``ak_bmsc`` cookie) which closes the connection on stripped requests; the
# Sec-Fetch-* headers and Accept-Encoding: br are what trip the challenge into
# returning the page instead of stalling.
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
    """JSF auto-generated IDs needed to build a valid TRF3 search payload.

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
    """Pull the dynamic ``j_idNNN`` IDs out of TRF3's form HTML."""
    def _find(pattern: str, label: str) -> str:
        m = re.search(pattern, form_html)
        if not m:
            raise RuntimeError(f"TRF3: could not locate {label} field in form HTML")
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
            "TRF3: could not locate executarPesquisa search trigger in form HTML"
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

    TRF3 specifics:

    * ``classeJudicial`` is an autocomplete component (with paired
      ``sgbClasseJudicial_selection``).
    * ``dataAutuacaoDecoration`` is rendered, so the date inputs are part of
      the expected payload (TRF5's form omits them).
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
