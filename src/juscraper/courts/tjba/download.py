"""
Downloads raw results from the TJBA jurisprudence search (GraphQL API).
"""


from juscraper.core.http import RequestFn
from juscraper.utils.pagination import baixar_paginas_pedidas, paginas_ate_o_teto, recusar_paginas_alem_do_teto
from juscraper.utils.params import to_iso_date

GRAPHQL_URL = "https://jurisprudenciaws.tjba.jus.br/graphql"
# O portal entrega só os 10.000 primeiros resultados de uma busca. Medido em
# 16/11/2026: quando ``(pageNumber + 1) * itemsPerPage`` passa de 10.000, a
# resposta é HTTP 200 com ``data: null`` e ``errors`` (com 10 por página, o
# ``pageNumber`` 999 responde e o 1000 falha; com 20, o 499 e o 500), embora
# ``pageCount`` informe o total inteiro (109.200 páginas em "dano moral").
MAX_RESULTS = 10_000

FILTER_QUERY = """
query filter(
  $decisaoFilter: DecisaoFilter!,
  $pageNumber: Int!,
  $itemsPerPage: Int!
) {
  filter(
    decisaoFilter: $decisaoFilter,
    pageNumber: $pageNumber,
    itemsPerPage: $itemsPerPage
  ) {
    decisoes {
      dataPublicacao
      relator { id nome }
      orgaoJulgador { id nome }
      classe { id descricao }
      conteudo
      tipoDecisao
      ementa
      hash
      numeroProcesso
    }
    relatores { key value }
    orgaos { key value }
    classes { key value }
    pageCount
    itemCount
  }
}
""".strip()


def _build_filter(
    pesquisa: str = "",
    numero_recurso: str | None = None,
    orgaos: list | None = None,
    relatores: list | None = None,
    classes: list | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    segundo_grau: bool = True,
    turmas_recursais: bool = True,
    tipo_acordaos: bool = True,
    tipo_decisoes_monocraticas: bool = True,
    ordenado_por: str = "dataPublicacao",
) -> dict:
    """Build the ``DecisaoFilter`` input for the GraphQL query."""
    filtro = {
        "assunto": pesquisa or "",
        "orgaos": orgaos or [],
        "relatores": relatores or [],
        "classes": classes or [],
        "dataInicial": _to_iso(data_publicacao_inicio) or "1980-02-01T03:00:00.000Z",
        "segundoGrau": segundo_grau,
        "turmasRecursais": turmas_recursais,
        "tipoAcordaos": tipo_acordaos,
        "tipoDecisoesMonocraticas": tipo_decisoes_monocraticas,
        "ordenadoPor": ordenado_por,
    }
    if data_publicacao_fim:
        filtro["dataFinal"] = _to_iso(data_publicacao_fim)
    if numero_recurso:
        filtro["numeroRecurso"] = numero_recurso
    return filtro


def _to_iso(date_str: str | None) -> str | None:
    """Convert ``DD/MM/YYYY`` or ``YYYY-MM-DD`` to ISO 8601 with timezone offset."""
    if not date_str:
        return None
    if "T" in date_str:
        return date_str
    iso = to_iso_date(date_str)
    return f"{iso}T03:00:00.000Z"


def cjsg_download(
    pesquisa: str = "",
    paginas=None,
    numero_recurso: str | None = None,
    orgaos: list | None = None,
    relatores: list | None = None,
    classes: list | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    segundo_grau: bool = True,
    turmas_recursais: bool = True,
    tipo_acordaos: bool = True,
    tipo_decisoes_monocraticas: bool = True,
    ordenado_por: str = "dataPublicacao",
    items_per_page: int = 10,
    *,
    request_fn: RequestFn,
) -> list:
    """
    Download raw results from TJBA jurisprudence search (multiple pages).

    Parameters
    ----------
    pesquisa : str
        Search term.
    paginas : list, range, or None
        Pages to download (1-based). None downloads all available pages.
    numero_recurso : str, optional
        Case/appeal number filter.
    items_per_page : int
        Results per page (default 10).
    request_fn : RequestFn
        HTTP callable that handles retry + raise_for_status — em uso normal e
        ``TJBAScraper._request_with_retry`` (via ``core.http.HTTPScraper``),
        centralizando backoff exponencial para 429/5xx.

    Returns
    -------
    list
        List of raw GraphQL response dicts (one per page).
    """
    decisao_filter = _build_filter(
        pesquisa=pesquisa,
        numero_recurso=numero_recurso,
        orgaos=orgaos,
        relatores=relatores,
        classes=classes,
        data_publicacao_inicio=data_publicacao_inicio,
        data_publicacao_fim=data_publicacao_fim,
        segundo_grau=segundo_grau,
        turmas_recursais=turmas_recursais,
        tipo_acordaos=tipo_acordaos,
        tipo_decisoes_monocraticas=tipo_decisoes_monocraticas,
        ordenado_por=ordenado_por,
    )

    def _fetch_page(page_number: int) -> dict:
        payload = {
            "operationName": "filter",
            "variables": {
                "decisaoFilter": decisao_filter,
                "pageNumber": page_number,
                "itemsPerPage": items_per_page,
            },
            "query": FILTER_QUERY,
        }
        resp = request_fn("POST", GRAPHQL_URL, json=payload, perfil="cjsg")
        data: dict = resp.json()
        if "errors" in data:
            raise ValueError(f"GraphQL errors: {data['errors']}")
        return data

    teto = MAX_RESULTS // items_per_page
    recusar_paginas_alem_do_teto(paginas, teto, tribunal="TJBA")

    def _n_pags(first: dict) -> int:
        page_count = ((first.get("data") or {}).get("filter") or {}).get("pageCount") or 1
        return paginas_ate_o_teto(paginas, page_count, teto, tribunal="TJBA")

    return baixar_paginas_pedidas(
        paginas, lambda pagina: _fetch_page(pagina - 1), _n_pags, tribunal="TJBA", sleep_time=1,
    )
