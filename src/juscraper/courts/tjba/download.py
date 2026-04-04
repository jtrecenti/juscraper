"""
Downloads raw results from the TJBA jurisprudence search (GraphQL API).
"""
import logging
import math
import time

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://jurisprudenciaws.tjba.jus.br/graphql"

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
    numero_recurso: str = None,
    orgaos: list = None,
    relatores: list = None,
    classes: list = None,
    data_publicacao_inicio: str = None,
    data_publicacao_fim: str = None,
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
    """Convert ``YYYY-MM-DD`` to ISO 8601 with timezone offset."""
    if not date_str:
        return None
    if "T" in date_str:
        return date_str
    return f"{date_str}T03:00:00.000Z"


def _fetch_page(
    session: requests.Session,
    decisao_filter: dict,
    page_number: int,
    items_per_page: int = 10,
    max_retries: int = 3,
) -> dict:
    """Fetch a single page from the TJBA GraphQL API (0-based)."""
    payload = {
        "operationName": "filter",
        "variables": {
            "decisaoFilter": decisao_filter,
            "pageNumber": page_number,
            "itemsPerPage": items_per_page,
        },
        "query": FILTER_QUERY,
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(GRAPHQL_URL, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise ValueError(f"GraphQL errors: {data['errors']}")
            return data
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning("TJBA request failed (attempt %d/%d): %s. Retrying in %ds...",
                           attempt, max_retries, exc, wait)
            time.sleep(wait)
    return {}  # unreachable, but satisfies type checkers


def cjsg_download(
    pesquisa: str = "",
    paginas=None,
    numero_recurso: str = None,
    orgaos: list = None,
    relatores: list = None,
    classes: list = None,
    data_publicacao_inicio: str = None,
    data_publicacao_fim: str = None,
    segundo_grau: bool = True,
    turmas_recursais: bool = True,
    tipo_acordaos: bool = True,
    tipo_decisoes_monocraticas: bool = True,
    ordenado_por: str = "dataPublicacao",
    items_per_page: int = 10,
    session: requests.Session = None,
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

    Returns
    -------
    list
        List of raw GraphQL response dicts (one per page).
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
            "Content-Type": "application/json",
        })

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

    if paginas is None:
        first = _fetch_page(session, decisao_filter, 0, items_per_page)
        resultados = [first]
        page_count = first.get("data", {}).get("filter", {}).get("pageCount", 1)
        if page_count > 1:
            for p in tqdm(range(1, page_count), desc="Baixando paginas TJBA"):
                resultados.append(_fetch_page(session, decisao_filter, p, items_per_page))
                time.sleep(1)
        return resultados

    paginas_list = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_list, desc="Baixando paginas TJBA"):
        resultados.append(
            _fetch_page(session, decisao_filter, pagina_1based - 1, items_per_page)
        )
        if len(paginas_list) > 1:
            time.sleep(1)
    return resultados
