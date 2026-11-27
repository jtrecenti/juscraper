"""HTTP-level helpers for the TJGO jurisprudence search."""
from __future__ import annotations

import math
import re
import time

from juscraper.core.avisos import avisar
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import extract_count_with_cascade, paginas_no_intervalo

from .parse import has_results

SEARCH_URL = "https://projudi.tjgo.jus.br/ConsultaJurisprudencia"
RESULTS_PER_PAGE = 10

AVISO_TURNSTILE = (
    "TJGO: a busca voltou sem resultados. Desde 12/11/2026 (Projudi 3.194.1) o "
    "portal exige o token Cloudflare Turnstile, que o juscraper não envia, e sem "
    "ele toda busca volta vazia, sem mensagem de erro. Se a busca deveria trazer "
    "resultados, o cjsg do TJGO está bloqueado por esse token."
)

_PAGINATION_CSS_SELECTORS: tuple[str, ...] = ("legend.formLocalizarLegenda",)
_PAGINATION_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(\d[\d\.]*)\s*resultados?\s+encontrados?", re.IGNORECASE),
    re.compile(r"(\d[\d\.]*)\s*resultados?", re.IGNORECASE),
)


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
    """Monta o corpo do formulario da busca do Projudi (TJGO).

    ``page`` e 1-based; o backend usa o deslocamento 0-based
    ``PosicaoPaginaAtual``, calculado aqui. ``cf-turnstile-response`` e
    ``g-recaptcha-response`` vao vazios: desde o Projudi 3.194.1 (12/11/2026) o
    servidor valida o token Cloudflare Turnstile em ``g-recaptcha-response`` e,
    sem ele, devolve o formulario sem resultados e sem erro (ver
    :data:`AVISO_TURNSTILE`).
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
    n = extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
    )
    return n if n is not None else 0


def _fetch_page(
    request_fn: RequestFn,
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
    resp = request_fn("POST", SEARCH_URL, data=payload, perfil="cjsg")
    resp.encoding = "iso-8859-1"
    return resp.text


def cjsg_download(
    pesquisa: str,
    paginas,
    *,
    request_fn: RequestFn,
    id_instancia: str,
    id_area: str,
    id_serventia_subtipo: str,
    data_publicacao_inicio: str,
    data_publicacao_fim: str,
    numero_processo: str,
    qtde_itens_pagina: int,
    sleep_time: float,
) -> list:
    """Run a TJGO search and return the raw HTML of each page.

    Args:
        request_fn: HTTP callable que aplica retry + ``raise_for_status``.
            Em uso normal e ``TJGOScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``).
    """
    # Prime the session (cookies) with a GET on the form.
    request_fn("GET", SEARCH_URL, perfil="formulario")

    first = _fetch_page(
        request_fn=request_fn,
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
    if not total and not has_results(first):
        # Com o token valido, uma busca sem resultados devolve o mesmo HTML da
        # busca bloqueada; por isso o aviso sai em toda busca vazia.
        avisar(AVISO_TURNSTILE)
    n_pags = max(1, math.ceil(total / qtde_itens_pagina)) if total else 1

    results: list = []
    for pagina in paginas_no_intervalo(paginas, n_pags, tribunal="TJGO"):
        if pagina == 1:
            results.append(first)
            continue
        time.sleep(sleep_time)
        html = _fetch_page(
            request_fn=request_fn,
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
