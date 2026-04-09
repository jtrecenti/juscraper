"""Downloads raw results from the TJPB jurisprudence search (Laravel API)."""
import logging
import math
import re
import time

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://pje-jurisprudencia.tjpb.jus.br"
SEARCH_URL = f"{BASE_URL}/api/jurisprudencia/pesquisar"
RESULTS_PER_PAGE = 10


def _get_csrf_token(session: requests.Session) -> str:
    """Fetch the CSRF token from the TJPB homepage meta tag."""
    resp = session.get(BASE_URL, timeout=30)
    resp.raise_for_status()
    match = re.search(r'<meta name="_token" content="([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("Could not find CSRF token on TJPB page.")
    return match.group(1)


def _build_payload(
    token: str,
    pesquisa: str,
    page: int = 1,
    teor: str = "",
    nr_processo: str = "",
    id_classe_judicial: str = "",
    id_orgao_julgador: str = "",
    id_relator: str = "",
    dt_inicio: str = "",
    dt_fim: str = "",
    id_origem: str = "8,2",
    decisoes: bool = False,
) -> dict:
    """Build the JSON payload for the TJPB search API."""
    return {
        "_token": token,
        "jurisprudencia": {
            "ementa": pesquisa,
            "teor": teor,
            "nr_rocesso": nr_processo,
            "id_classe_judicial": id_classe_judicial,
            "id_orgao_julgador": id_orgao_julgador,
            "id_relator": id_relator,
            "dt_inicio": dt_inicio,
            "dt_fim": dt_fim,
            "id_origem": id_origem,
            "decisoes": decisoes,
        },
        "page": page,
    }


def _fetch_page(session: requests.Session, payload: dict, max_retries: int = 3) -> dict:
    """Fetch a single page from the TJPB API with retry logic."""
    headers = {"X-Requested-With": "XMLHttpRequest"}
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(SEARCH_URL, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJPB request failed (attempt %d/%d): %s. Retrying in %ds...",
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
    """Download raw results from the TJPB jurisprudence search.

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

    token = _get_csrf_token(session)

    def _get_page(pagina_1based):
        payload = _build_payload(token, pesquisa, page=pagina_1based, **kwargs)
        data = _fetch_page(session, payload)
        time.sleep(1)
        return data

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        total = first.get("total", 0)
        n_pags = math.ceil(total / RESULTS_PER_PAGE) if total else 1
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJPB"):
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJPB"):
        resultados.append(_get_page(pagina_1based))
    return resultados
