"""HTTP-level helpers for the TJRJ jurisprudence search."""
from __future__ import annotations

import logging
import math
import re
import time

import requests

logger = logging.getLogger("juscraper.tjrj")

FORM_URL = "https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx"
RESULT_URL = (
    "https://www3.tjrj.jus.br/EJURIS/ProcessarConsJurisES.aspx"
    "/ExecutarConsultarJurisprudencia"
)
RESULTS_PER_PAGE = 10

_FIELD_PREFIX = "ctl00$ContentPlaceHolder1$"
_BLOCKED_WORDS_FIELD = f"{_FIELD_PREFIX}hfListaPalavrasBloqueadas"

_HIDDEN_RE = re.compile(
    r'<input[^>]*name="(?P<name>__VIEWSTATE|__VIEWSTATEGENERATOR|__EVENTVALIDATION'
    r'|ctl00\$ContentPlaceHolder1\$hfListaPalavrasBloqueadas)"[^>]*value="(?P<value>[^"]*)"',
    re.IGNORECASE,
)


def extract_viewstate_fields(html: str) -> dict:
    """Extrai os quatro hidden fields exigidos pelo POST ASP.NET do TJRJ.

    Retorna ``__VIEWSTATE``, ``__VIEWSTATEGENERATOR``, ``__EVENTVALIDATION`` e
    ``ctl00$ContentPlaceHolder1$hfListaPalavrasBloqueadas``. Campos ausentes
    sao omitidos do dict — o caller substitui defaults explicitamente.

    O hidden de palavras bloqueadas carrega a stopword list do backend
    (``"A;ACIMA;COM;..."``); o servidor le esse valor de volta para validar o
    termo de busca, e um POST que omite o campo pode disparar 500 Runtime
    Error em janelas onde o backend espera o roundtrip (refs #143, exposto
    em 2026-04-30).
    """
    fields: dict = {}
    for match in _HIDDEN_RE.finditer(html):
        fields[match.group("name")] = match.group("value")
    return fields


def build_cjsg_payload(
    hidden: dict,
    pesquisa: str,
    *,
    ano_inicio: str = "",
    ano_fim: str = "",
    competencia: str = "1",
    origem: str = "1",
    tipo_acordao: bool = True,
    tipo_monocratica: bool = True,
    magistrado_codigo: str | None = None,
    orgao_codigo: str | None = None,
) -> dict:
    """Monta o body URL-encoded para o POST ASPX do TJRJ.

    ``hidden`` carrega os quatro hidden fields devolvidos por
    :func:`extract_viewstate_fields`. ``g-recaptcha-response`` fica vazio
    propositalmente — o widget e decorativo, o backend nao valida o token.
    """
    data = {
        "__EVENTTARGET": f"{_FIELD_PREFIX}btnPesquisar",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
        _BLOCKED_WORDS_FIELD: hidden.get(_BLOCKED_WORDS_FIELD, ""),
        f"{_FIELD_PREFIX}hfCodRamos": "",
        f"{_FIELD_PREFIX}hfCodMags": magistrado_codigo or "",
        f"{_FIELD_PREFIX}hfCodOrgs": orgao_codigo or "",
        f"{_FIELD_PREFIX}txtTextoPesq": pesquisa,
        f"{_FIELD_PREFIX}cmbOrigem": origem,
        f"{_FIELD_PREFIX}cmbAnoInicio": ano_inicio,
        f"{_FIELD_PREFIX}cmbAnoFim": ano_fim,
        f"{_FIELD_PREFIX}cmbCompetencia": competencia,
        f"{_FIELD_PREFIX}cmbRamo": "",
        f"{_FIELD_PREFIX}cmbMagistrado": "",
        f"{_FIELD_PREFIX}chkAtivo": "on",
        f"{_FIELD_PREFIX}chkInativo": "on",
        f"{_FIELD_PREFIX}cmbOrgaoJulgador": "",
        f"{_FIELD_PREFIX}cmbTipNumeracao": "1",
        f"{_FIELD_PREFIX}txtNumeracao": "",
        f"{_FIELD_PREFIX}chkIntTeor": "on",
        f"{_FIELD_PREFIX}chkEmentario": "on",
        "g-recaptcha-response": "",
    }
    if tipo_acordao:
        data[f"{_FIELD_PREFIX}chkAcordao"] = "on"
    if tipo_monocratica:
        data[f"{_FIELD_PREFIX}chkDecMon"] = "on"
    return data


def _init_session(
    session: requests.Session,
    pesquisa: str,
    ano_inicio: str | None,
    ano_fim: str | None,
    competencia: str,
    origem: str,
    tipo_acordao: bool,
    tipo_monocratica: bool,
    magistrado_codigo: str | None,
    orgao_codigo: str | None,
) -> None:
    """Submit the search form so the result XHR has a valid server session."""
    resp = session.get(FORM_URL, timeout=30)
    resp.raise_for_status()
    hidden = extract_viewstate_fields(resp.text)
    data = build_cjsg_payload(
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
    data: dict = resp.json().get("d", {})
    return data


def cjsg_download(
    session: requests.Session,
    pesquisa: str,
    paginas,
    ano_inicio: str | None,
    ano_fim: str | None,
    competencia: str,
    origem: str,
    tipo_acordao: bool,
    tipo_monocratica: bool,
    magistrado_codigo: str | None,
    orgao_codigo: str | None,
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
