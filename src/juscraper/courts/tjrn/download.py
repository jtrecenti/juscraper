"""Downloads raw results from the TJRN jurisprudence search (Elasticsearch API)."""
import math
import time

from tqdm import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import menor_pagina, paginas_no_intervalo

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
        "usuario": {"matricula": "", "token": ""},  # nosec
    }


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    sleep_time: float = 1.0,
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
        sleep_time: Delay (em segundos) entre páginas. Default 1.0; o client
            normalmente passa ``self.sleep_time`` herdado de ``HTTPScraper``.
        **kwargs: Additional filter parameters.
    """
    def _get_page(pagina_1based):
        payload = build_cjsg_payload(pesquisa, page=pagina_1based, **kwargs)
        resp = request_fn("POST", BASE_URL, json=payload, timeout=30)
        data: dict = resp.json()
        return data

    # A menor página pedida sai primeiro, porque traz o total; as demais, na
    # ordem pedida, uma vez cada, e as além do total vão para o log.
    primeira = menor_pagina(paginas)
    first = _get_page(primeira)
    total = first.get("hits", {}).get("total", 0)
    n_pags = math.ceil(total / RESULTS_PER_PAGE) if total else 1
    resultados = []
    for pagina in tqdm(paginas_no_intervalo(paginas, n_pags, tribunal="TJRN"), desc="Baixando CJSG TJRN"):
        if pagina == primeira:
            resultados.append(first)
            continue
        time.sleep(sleep_time)
        resultados.append(_get_page(pagina))
    return resultados
