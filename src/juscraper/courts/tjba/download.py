"""
Downloads raw results from the TJBA jurisprudence search (GraphQL API).
"""

from datetime import date
from functools import partial

from juscraper.core.http import RequestFn
from juscraper.utils.divisao_por_data import BuscaComTeto, baixar_dividindo_por_data
from juscraper.utils.pagination import baixar_paginas_pedidas, contador_com_teto
from juscraper.utils.params import to_iso_date

from .parse import cjsg_parse

GRAPHQL_URL = "https://jurisprudenciaws.tjba.jus.br/graphql"
# O portal entrega só os 10.000 primeiros resultados de uma busca. Medido em
# 16/11/2026: quando ``(pageNumber + 1) * itemsPerPage`` passa de 10.000, a
# resposta é HTTP 200 com ``data: null`` e ``errors`` (com 10 por página, o
# ``pageNumber`` 999 responde e o 1000 falha; com 20, o 499 e o 500), embora
# ``pageCount`` informe o total inteiro (109.200 páginas em "dano moral").
MAX_RESULTS = 10_000
# Início que o portal já recebe quando a busca não informa
# ``data_publicacao_inicio``, e início das janelas da busca dividida por data.
# Medido em 16/11/2026: em "dano moral", os 1.091.994 resultados têm data de
# publicação entre essa data e o dia da medição.
PISO_DATA_PUBLICACAO = date(1980, 2, 1)

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
        "dataInicial": _to_iso(data_publicacao_inicio or PISO_DATA_PUBLICACAO.isoformat()),
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


def _chave_da_decisao(decisao: dict) -> tuple:
    """Identifica a linha de uma decisão, para retirar a que o portal devolver em duas janelas de data.

    O ``hash`` sozinho não serve: é do texto. Medido em 16/11/2026, em "dano
    moral" de 01/01 a 20/02/2024: 444 das 11.361 linhas repetem o ``hash`` de
    outra, com outro órgão julgador, outra data de publicação ou outro
    processo, e 3 vêm sem ``hash``.
    """
    return (
        decisao.get("hash"),
        decisao.get("numeroProcesso"),
        decisao.get("dataPublicacao"),
        (decisao.get("orgaoJulgador") or {}).get("id"),
    )


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
    auto_chunk: bool = True,
    *,
    request_fn: RequestFn,
) -> list:
    """Baixa os resultados brutos da pesquisa de jurisprudência do TJBA (várias páginas).

    Args:
        pesquisa: Termo de busca.
        paginas (list | range | None): Páginas a baixar (1-based). ``None``
            baixa todas as páginas disponíveis.
        numero_recurso: Número do processo/recurso.
        orgaos: Lista de IDs de órgão julgador.
        relatores: Lista de IDs de relator.
        classes: Lista de IDs de classe.
        data_publicacao_inicio: Data inicial de publicação.
        data_publicacao_fim: Data final de publicação.
        segundo_grau: Inclui resultados do segundo grau.
        turmas_recursais: Inclui resultados das turmas recursais.
        tipo_acordaos: Inclui acórdãos.
        tipo_decisoes_monocraticas: Inclui decisões monocráticas.
        ordenado_por: ``"dataPublicacao"`` ou ``"relevancia"``.
        items_per_page: Resultados por página (default 10).
        auto_chunk: Com ``paginas=None``, divide por data de publicação a busca
            que passa de ``MAX_RESULTS`` (ver
            :func:`juscraper.utils.divisao_por_data.baixar_dividindo_por_data`).
        request_fn: Função HTTP que cuida do retry e do ``raise_for_status``; em
            uso normal, ``TJBAScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), que centraliza o backoff exponencial para
            429/5xx.

    Returns:
        Lista dos dicionários brutos da resposta GraphQL, um por página.
    """
    filtro_da_janela = partial(
        _build_filter,
        pesquisa=pesquisa,
        numero_recurso=numero_recurso,
        orgaos=orgaos,
        relatores=relatores,
        classes=classes,
        segundo_grau=segundo_grau,
        turmas_recursais=turmas_recursais,
        tipo_acordaos=tipo_acordaos,
        tipo_decisoes_monocraticas=tipo_decisoes_monocraticas,
        ordenado_por=ordenado_por,
    )

    def _fetch_page(page_number: int, inicio: str | None, fim: str | None) -> dict:
        payload = {
            "operationName": "filter",
            "variables": {
                "decisaoFilter": filtro_da_janela(data_publicacao_inicio=inicio, data_publicacao_fim=fim),
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

    def _filter(first: dict) -> dict:
        return (first.get("data") or {}).get("filter") or {}

    if paginas is None and auto_chunk:
        busca: BuscaComTeto[dict] = BuscaComTeto(
            tribunal="TJBA",
            rotulo="data_publicacao",
            teto=MAX_RESULTS,
            por_pagina=items_per_page,
            piso=PISO_DATA_PUBLICACAO,
            buscar=lambda inicio, fim, pagina: _fetch_page(pagina - 1, inicio, fim),
            contar_resultados=lambda first: _filter(first).get("itemCount") or 0,
            itens=lambda pagina: _filter(pagina).get("decisoes") or [],
            chave=_chave_da_decisao,
            parse=cjsg_parse,
            sleep_time=1,
        )
        return baixar_dividindo_por_data(
            busca, to_iso_date(data_publicacao_inicio) or None, to_iso_date(data_publicacao_fim) or None
        )

    def _n_pags(first: dict) -> int:
        page_count: int = _filter(first).get("pageCount") or 1
        return page_count

    contar = contador_com_teto(paginas, MAX_RESULTS // items_per_page, _n_pags, tribunal="TJBA")
    return baixar_paginas_pedidas(
        paginas,
        lambda pagina: _fetch_page(pagina - 1, data_publicacao_inicio, data_publicacao_fim),
        contar,
        tribunal="TJBA",
        sleep_time=1,
    )
