"""HTTP-level helpers for the TJRJ jurisprudence search."""
from __future__ import annotations

import logging
import math
import re
import time
from typing import Optional

import requests

logger = logging.getLogger("juscraper.tjrj")

FORM_URL = "https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx"
RESULT_URL = (
    "https://www3.tjrj.jus.br/EJURIS/ProcessarConsJurisES.aspx"
    "/ExecutarConsultarJurisprudencia"
)
RESULTS_PER_PAGE = 10

_HIDDEN_RE = re.compile(
    r'<input[^>]*name="(__VIEWSTATE|__VIEWSTATEGENERATOR|__EVENTVALIDATION)"'
    r'[^>]*value="([^"]*)"',
    re.IGNORECASE,
)


def _scrape_hidden(html: str) -> dict:
    fields = {}
    for match in _HIDDEN_RE.finditer(html):
        fields[match.group(1)] = match.group(2)
    return fields


def _build_form_data(
    hidden: dict,
    pesquisa: str,
    ano_inicio: str,
    ano_fim: str,
    competencia: str,
    origem: str,
    tipo_acordao: bool,
    tipo_monocratica: bool,
    magistrado_codigo: Optional[str],
    orgao_codigo: Optional[str],
) -> dict:
    data = {
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnPesquisar",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
        "ctl00$ContentPlaceHolder1$hfCodRamos": "",
        "ctl00$ContentPlaceHolder1$hfCodMags": magistrado_codigo or "",
        "ctl00$ContentPlaceHolder1$hfCodOrgs": orgao_codigo or "",
        "ctl00$ContentPlaceHolder1$txtTextoPesq": pesquisa,
        "ctl00$ContentPlaceHolder1$cmbOrigem": origem,
        "ctl00$ContentPlaceHolder1$cmbAnoInicio": ano_inicio,
        "ctl00$ContentPlaceHolder1$cmbAnoFim": ano_fim,
        "ctl00$ContentPlaceHolder1$cmbCompetencia": competencia,
        "ctl00$ContentPlaceHolder1$cmbRamo": "",
        "ctl00$ContentPlaceHolder1$cmbMagistrado": "",
        "ctl00$ContentPlaceHolder1$chkAtivo": "on",
        "ctl00$ContentPlaceHolder1$chkInativo": "on",
        "ctl00$ContentPlaceHolder1$cmbOrgaoJulgador": "",
        "ctl00$ContentPlaceHolder1$cmbTipNumeracao": "1",
        "ctl00$ContentPlaceHolder1$txtNumeracao": "",
        "ctl00$ContentPlaceHolder1$chkIntTeor": "on",
        "ctl00$ContentPlaceHolder1$chkEmentario": "on",
        # Decorative reCAPTCHA: backend does not validate the token.
        "g-recaptcha-response": "",
    }
    if tipo_acordao:
        data["ctl00$ContentPlaceHolder1$chkAcordao"] = "on"
    if tipo_monocratica:
        data["ctl00$ContentPlaceHolder1$chkDecMon"] = "on"
    return data


def _init_session(
    session: requests.Session,
    pesquisa: str,
    ano_inicio: Optional[str],
    ano_fim: Optional[str],
    competencia: str,
    origem: str,
    tipo_acordao: bool,
    tipo_monocratica: bool,
    magistrado_codigo: Optional[str],
    orgao_codigo: Optional[str],
) -> None:
    """Submit the search form so the result XHR has a valid server session."""
    resp = session.get(FORM_URL, timeout=30)
    resp.raise_for_status()
    hidden = _scrape_hidden(resp.text)
    data = _build_form_data(
        hidden=hidden,
        pesquisa=pesquisa,
        ano_inicio=ano_inicio or "",
        ano_fim=ano_fim or "",
        competencia=competencia,
        origem=origem,
        tipo_acordao=tipo_acordao,
        tipo_monocratica=tipo_monocratica,
        magistrado_codigo=magistrado_codigo,
        orgao_codigo=orgao_codigo,
    )
    resp2 = session.post(FORM_URL, data=data, allow_redirects=True, timeout=30)
    resp2.raise_for_status()


def _fetch_page(session: requests.Session, num_pagina_0: int) -> dict:
    payload = {"numPagina": num_pagina_0, "pageSeq": "0"}
    resp = session.post(
        RESULT_URL,
        json=payload,
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=60,
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.json().get("d", {})


def cjsg_download(
    session: requests.Session,
    pesquisa: str,
    paginas,
    ano_inicio: Optional[str],
    ano_fim: Optional[str],
    competencia: str,
    origem: str,
    tipo_acordao: bool,
    tipo_monocratica: bool,
    magistrado_codigo: Optional[str],
    orgao_codigo: Optional[str],
    sleep_time: float,
) -> list:
    """Run a TJRJ search and return the raw JSON page payloads."""
    _init_session(
        session=session,
        pesquisa=pesquisa,
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
        competencia=competencia,
        origem=origem,
        tipo_acordao=tipo_acordao,
        tipo_monocratica=tipo_monocratica,
        magistrado_codigo=magistrado_codigo,
        orgao_codigo=orgao_codigo,
    )
    first = _fetch_page(session, 0)
    total = int(first.get("TotalDocs") or 0)
    n_pags = max(1, math.ceil(total / RESULTS_PER_PAGE)) if total else 1

    if paginas is None:
        paginas = range(1, n_pags + 1)

    results: list = []
    for pagina in paginas:
        if pagina < 1 or pagina > n_pags:
            logger.warning("TJRJ: pagina %s fora do intervalo 1-%s", pagina, n_pags)
            continue
        if pagina == 1:
            results.append(first)
            continue
        time.sleep(sleep_time)
        data = _fetch_page(session, pagina - 1)
        results.append(data)
    return results
