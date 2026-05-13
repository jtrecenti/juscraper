"""Downloads raw results from the TJRN jurisprudence search (Elasticsearch API)."""
import logging
import math
import time
from collections.abc import Callable

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.tjrn.jus.br/api/pesquisar"
RESULTS_PER_PAGE = 10


def build_cjsg_payload(
    pesquisa: str,
    page: int = 1,
    inteiro_teor: str = "",
    nr_processo: str = "",
    id_classe: str = "",
    id_orgao_julgador: str = "",
    id_relator: str = "",
    id_colegiado: str = "",
    id_juiz: str = "",
    id_vara: str = "",
    dt_inicio: str = "",
    dt_fim: str = "",
    origem: str = "",
    sistema: str = "",
    decisoes: str = "",
    jurisdicoes: str = "",
    grau: str = "",
) -> dict:
    """Build the JSON payload for the TJRN CJSG search API.

    The public parameter ``id_classe`` is the canonical name; the backend
    PJe field is ``id_classe_judicial`` and stays unchanged.
    """
    return {
        "jurisprudencia": {
            "ementa": pesquisa,
            "inteiro_teor": inteiro_teor,
            "nr_processo": nr_processo,
            "id_classe_judicial": id_classe,
            "id_orgao_julgador": id_orgao_julgador,
            "id_relator": id_relator,
            "id_colegiado": id_colegiado,
            "id_juiz": id_juiz,
            "id_vara": id_vara,
            "dt_inicio": dt_inicio,
            "dt_fim": dt_fim,
            "origem": origem,
            "sistema": sistema,
            "decisoes": decisoes,
            "jurisdicoes": jurisdicoes,
            "grau": grau,
        },
        "page": page,
        "usuario": {"matricula": "", "token": ""},
    }


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: Callable[..., requests.Response],
    **kwargs,
) -> list:
    """Download raw results from the TJRN jurisprudence search.

    Returns a list of raw JSON responses (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJRNScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx.
        **kwargs: Additional filter parameters.
    """
    def _get_page(pagina_1based):
        payload = build_cjsg_payload(pesquisa, page=pagina_1based, **kwargs)
        resp = request_fn("POST", BASE_URL, json=payload, timeout=30)
        data: dict = resp.json()
        time.sleep(1)
        return data

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        total = first.get("hits", {}).get("total", 0)
        n_pags = math.ceil(total / RESULTS_PER_PAGE) if total else 1
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJRN"):
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJRN"):
        resultados.append(_get_page(pagina_1based))
    return resultados
