"""
Functions for downloading specific to TJDFT
"""
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import resolve_total_pages

BASE_URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
# Maior ``tamanho`` que a API aceita; acima disso ela responde HTTP 400.
MAX_TAMANHO_PAGINA = 40


def build_cjsg_payload(
    query: str,
    pagina: int,
    *,
    sinonimos: bool = True,
    espelho: bool = True,
    buscar_em: str = "ementa",
    quantidade_por_pagina: int = 10,
    termos_acessorios: list | None = None,
) -> dict:
    """Build the JSON payload sent to the TJDFT jurisprudence search API.

    ``pagina`` vai como está no campo ``pagina`` da API, que conta a partir de
    0: a primeira página de resultados é ``pagina=0``. ``cjsg_download`` recebe
    páginas 1-based e subtrai 1.

    ``buscar_em="inteiro_teor"`` liga ``inteiroTeor``, que soma o inteiro
    teor aos campos buscados.

    Shared between the scraper and the offline capture script so both stay
    in sync with the API contract.
    """
    return {
        "query": query,
        "termosAcessorios": list(termos_acessorios) if termos_acessorios else [],
        "pagina": pagina,
        "tamanho": quantidade_por_pagina,
        "sinonimos": sinonimos,
        "espelho": espelho,
        "inteiroTeor": buscar_em == "inteiro_teor",
        "retornaInteiroTeor": False,
        "retornaTotalizacao": True,
    }


def cjsg_download(
    query,
    paginas=None,
    *,
    request_fn: RequestFn,
    sinonimos=True,
    espelho=True,
    buscar_em="ementa",
    quantidade_por_pagina=10,
    base_url=BASE_URL,
    data_julgamento_inicio=None,
    data_julgamento_fim=None,
    data_publicacao_inicio=None,
    data_publicacao_fim=None,
):
    """
    Downloads raw results from the TJDFT jurisprudence search.
    Returns a list of raw results (JSON).

    Args:
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
        request_fn: HTTP callable que aplica retry + ``raise_for_status``.
            Em uso normal e ``TJDFTScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``).
    """
    headers = {"Content-Type": "application/json"}

    termos_acessorios: list = []
    # Datas chegam aqui ja em BACKEND_DATE_FORMAT (%Y-%m-%d) — coercao feita
    # por apply_input_pipeline_search no client a partir do schema.
    if data_julgamento_inicio and data_julgamento_fim:
        termos_acessorios.append(
            {"campo": "dataJulgamento", "valor": f"entre {data_julgamento_inicio} e {data_julgamento_fim}"}
        )
    if data_publicacao_inicio and data_publicacao_fim:
        termos_acessorios.append(
            {"campo": "dataPublicacao", "valor": f"entre {data_publicacao_inicio} e {data_publicacao_fim}"}
        )

    def _fetch_page(pagina):
        payload = build_cjsg_payload(
            query,
            pagina - 1,
            sinonimos=sinonimos,
            espelho=espelho,
            buscar_em=buscar_em,
            quantidade_por_pagina=quantidade_por_pagina,
            termos_acessorios=termos_acessorios,
        )
        resp = request_fn("POST", base_url, json=payload, headers=headers, perfil="cjsg")
        return resp.json()

    resultados = []
    if paginas is None:
        data = _fetch_page(1)
        resultados.extend(data.get("registros", []))
        n_pags = resolve_total_pages(
            (data.get("hits") or {}).get("value"),
            resultados_por_pagina=quantidade_por_pagina,
            tribunal="TJDFT",
        )
        paginas = range(2, n_pags + 1)
    for pagina in paginas:
        resultados.extend(_fetch_page(pagina).get("registros", []))
    return resultados
