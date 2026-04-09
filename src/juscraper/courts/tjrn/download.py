"""Downloads raw results from the TJRN jurisprudence search (Elasticsearch API)."""
import logging
import math
import time

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.tjrn.jus.br/api/pesquisar"
RESULTS_PER_PAGE = 10


def _build_payload(
    pesquisa: str,
    page: int = 1,
    inteiro_teor: str = "",
    nr_processo: str = "",
    id_classe_judicial: str = "",
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
    """Build the JSON payload for the TJRN search API."""
    return {
        "jurisprudencia": {
            "ementa": pesquisa,
            "inteiro_teor": inteiro_teor,
            "nr_processo": nr_processo,
            "id_classe_judicial": id_classe_judicial,
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


def _fetch_page(session: requests.Session, payload: dict, max_retries: int = 3) -> dict:
    """Fetch a single page from the TJRN API with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJRN request failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return {}  # unreachable


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    session: requests.Session = None,
    **kwargs,
) -> list:
    """Download raw results from the TJRN jurisprudence search.

    Returns a list of raw JSON responses (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        session: Optional requests.Session to reuse.
        **kwargs: Additional filter parameters.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def _get_page(pagina_1based):
        payload = _build_payload(pesquisa, page=pagina_1based, **kwargs)
        data = _fetch_page(session, payload)
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
