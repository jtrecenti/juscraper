"""Downloads raw results from the TJPB jurisprudence search (Laravel API)."""
import math
import time
from urllib.parse import unquote

import requests
from tqdm import tqdm

from juscraper.core.http import RequestFn

BASE_URL = "https://pje-jurisprudencia.tjpb.jus.br"
CLASSES_URL = f"{BASE_URL}/api/pje/classes/list"
SEARCH_URL = f"{BASE_URL}/api/jurisprudencia/pesquisar"
RESULTS_PER_PAGE = 10


def fetch_csrf_token(request_fn: RequestFn, session: requests.Session) -> str:
    """Fetch the CSRF cookie used by the TJPB search API."""
    request_fn("GET", CLASSES_URL, timeout=30)
    token = session.cookies.get("XSRF-TOKEN")
    if not token:
        raise RuntimeError("Could not find XSRF-TOKEN cookie on TJPB API session.")
    return unquote(token)


def build_cjsg_payload(
    pesquisa: str,
    page: int = 1,
    *,
    teor: str = "",
    nr_processo: str = "",
    id_classe: str = "",
    id_orgao_julgador: str = "",
    id_relator: str = "",
    dt_inicio: str = "",
    dt_fim: str = "",
    id_origem: str = "8,2",
    decisoes: bool = False,
) -> dict:
    """Build the JSON payload for the TJPB search API.

    The ``nr_rocesso`` (sic) key matches the backend spelling — do not
    rename it without confirming the live API still accepts it.
    """
    return {
        "jurisprudencia": {
            "ementa": pesquisa,
            "teor": teor,
            "nr_rocesso": nr_processo,
            "id_classe_judicial": id_classe,
            "id_orgao_julgador": id_orgao_julgador,
            "id_relator": id_relator,
            "dt_inicio": dt_inicio,
            "dt_fim": dt_fim,
            "id_origem": id_origem,
            "decisoes": decisoes,
        },
        "page": page,
    }


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    session: requests.Session,
    **kwargs,
) -> list:
    """Download raw results from the TJPB jurisprudence search.

    Returns a list of raw JSON responses (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJPBScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx.
        session: Shared HTTP session that receives the CSRF cookie.
        **kwargs: Additional filter parameters.
    """
    xsrf_token = fetch_csrf_token(request_fn, session)
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "X-XSRF-TOKEN": xsrf_token,
    }

    def _get_page(pagina_1based):
        payload = build_cjsg_payload(pesquisa, page=pagina_1based, **kwargs)
        resp = request_fn(
            "POST",
            SEARCH_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )
        data: dict = resp.json()
        time.sleep(1)
        return data

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        total = first.get("total", 0)
        n_pags = math.ceil(total / RESULTS_PER_PAGE) if total else 1
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJPB"):
                # laco de I/O (rede por iteracao sob tqdm): comprehension esconderia o efeito
                resultados.append(_get_page(pagina))  # noqa: PERF401
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJPB"):
        resultados.append(_get_page(pagina_1based))
    return resultados
