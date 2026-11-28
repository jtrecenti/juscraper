"""HTTP-level helpers for the TJGO jurisprudence search."""
from __future__ import annotations

import functools
import re
import time

from juscraper.core.avisos import avisar
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import Paginas, baixar_paginas_pedidas, extract_count_with_cascade, resolve_total_pages

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


def _extract_total(html: str) -> int | None:
    """Lê o total do ``legend``; ``None`` sem ele, como na busca vazia ou bloqueada."""
    return extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
    )


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
    paginas: Paginas | None,
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

    Raises:
        ValueError: Quando a página 1 traz resultados sem o total (markup novo).
    """
    # Prime the session (cookies) with a GET on the form.
    request_fn("GET", SEARCH_URL, perfil="formulario")
    buscar_pagina = functools.partial(
        _fetch_page,
        request_fn=request_fn,
        pesquisa=pesquisa,
        id_instancia=id_instancia,
        id_area=id_area,
        id_serventia_subtipo=id_serventia_subtipo,
        data_publicacao_inicio=data_publicacao_inicio,
        data_publicacao_fim=data_publicacao_fim,
        numero_processo=numero_processo,
        qtde_itens_pagina=qtde_itens_pagina,
    )
    # A busca abre na página 1, que traz o total; as demais saem pelo laço
    # comum, que devolve esta quando ela é pedida.
    first = buscar_pagina(page=1)
    total = _extract_total(first)
    if not total and not has_results(first):
        # Com o token valido, uma busca sem resultados devolve o mesmo HTML da
        # busca bloqueada; por isso o aviso sai em toda busca vazia. Esse HTML
        # nao traz marcador proprio: a falta de resultados e o unico sinal.
        avisar(AVISO_TURNSTILE)
        n_pags = 1
    else:
        n_pags = resolve_total_pages(total, resultados_por_pagina=qtde_itens_pagina, tribunal="TJGO")

    def buscar(pagina: int) -> str:
        if pagina == 1:
            return first
        time.sleep(sleep_time)
        return buscar_pagina(page=pagina)

    return baixar_paginas_pedidas(paginas, buscar, lambda _primeira: n_pags, tribunal="TJGO")
