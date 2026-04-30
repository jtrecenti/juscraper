"""HTTP-level helpers for the TJGO jurisprudence search."""
from __future__ import annotations

import logging
import math
import re
import time

import requests

logger = logging.getLogger("juscraper.tjgo")

SEARCH_URL = "https://projudi.tjgo.jus.br/ConsultaJurisprudencia"
RESULTS_PER_PAGE = 10
_TOTAL_RE = re.compile(r"(\d[\d\.]*)\s*resultados?", re.IGNORECASE)


def build_cjsg_payload(
    pesquisa: str,
    page: int = 1,
    *,
    id_instancia: str | int = "0",
    id_area: str | int = "0",
    id_serventia_subtipo: str | int = "0",
    numero_processo: str = "",
    data_publicacao_inicio: str = "",
    data_publicacao_fim: str = "",
    qtde_itens_pagina: int = RESULTS_PER_PAGE,
) -> dict:
    """Build the form-encoded body for the TJGO Projudi search endpoint.

    ``page`` is 1-based; the backend uses a 0-based ``PosicaoPaginaAtual``
    offset, which this helper computes. ``cf-turnstile-response`` is sent
    empty: the widget exists on the page but the backend does not validate
    the token.
    """
    return {
        "PaginaAtual": "2",
        "PosicaoPaginaAtual": str(page - 1),
        "Viewstate": "",
        "Texto": pesquisa,
        "Id_Instancia": str(id_instancia),
        "Id_Area": str(id_area),
        "Id_ServentiaSubTipo": str(id_serventia_subtipo),
        "Serventia": "",
        "Id_Serventia": "",
        "Usuario": "",
        "Id_Usuario": "",
        "ArquivoTipo": "",
        "Id_ArquivoTipo": "",
        "ProcessoNumero": numero_processo,
        "DataInicial": data_publicacao_inicio,
        "DataFinal": data_publicacao_fim,
        "cf-turnstile-response": "",
        "g-recaptcha-response": "",
        "Localizar": "Consultar",
        "qtdeItensPagina": str(qtde_itens_pagina),
    }


def _extract_total(html: str) -> int:
    match = _TOTAL_RE.search(html)
    if not match:
        return 0
    raw = match.group(1).replace(".", "").replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return 0


def _fetch_page(
    session: requests.Session,
    pesquisa: str,
    page: int,
    id_instancia: str,
    id_area: str,
    id_serventia_subtipo: str,
    data_publicacao_inicio: str,
    data_publicacao_fim: str,
    numero_processo: str,
    qtde_itens_pagina: int,
) -> str:
    payload = build_cjsg_payload(
        pesquisa=pesquisa,
        page=page,
        id_instancia=id_instancia,
        id_area=id_area,
        id_serventia_subtipo=id_serventia_subtipo,
        data_publicacao_inicio=data_publicacao_inicio,
        data_publicacao_fim=data_publicacao_fim,
        numero_processo=numero_processo,
        qtde_itens_pagina=qtde_itens_pagina,
    )
    resp = session.post(SEARCH_URL, data=payload, timeout=90)
    resp.raise_for_status()
    resp.encoding = "iso-8859-1"
    return resp.text


def cjsg_download(
    session: requests.Session,
    pesquisa: str,
    paginas,
    id_instancia: str,
    id_area: str,
    id_serventia_subtipo: str,
    data_publicacao_inicio: str,
    data_publicacao_fim: str,
    numero_processo: str,
    qtde_itens_pagina: int,
    sleep_time: float,
) -> list:
    """Run a TJGO search and return the raw HTML of each page."""
    # Prime the session (cookies) with a GET on the form.
    session.get(SEARCH_URL, timeout=60)

    first = _fetch_page(
        session=session,
        pesquisa=pesquisa,
        page=1,
        id_instancia=id_instancia,
        id_area=id_area,
        id_serventia_subtipo=id_serventia_subtipo,
        data_publicacao_inicio=data_publicacao_inicio,
        data_publicacao_fim=data_publicacao_fim,
        numero_processo=numero_processo,
        qtde_itens_pagina=qtde_itens_pagina,
    )
    total = _extract_total(first)
    n_pags = max(1, math.ceil(total / qtde_itens_pagina)) if total else 1

    if paginas is None:
        paginas = range(1, n_pags + 1)

    results: list = []
    for pagina in paginas:
        if pagina < 1 or pagina > n_pags:
            logger.warning("TJGO: pagina %s fora do intervalo 1-%s", pagina, n_pags)
            continue
        if pagina == 1:
            results.append(first)
            continue
        time.sleep(sleep_time)
        html = _fetch_page(
            session=session,
            pesquisa=pesquisa,
            page=pagina,
            id_instancia=id_instancia,
            id_area=id_area,
            id_serventia_subtipo=id_serventia_subtipo,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            numero_processo=numero_processo,
            qtde_itens_pagina=qtde_itens_pagina,
        )
        results.append(html)
    return results
