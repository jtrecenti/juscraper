"""Downloads raw results from the TJPB jurisprudence search (Laravel API)."""
import logging
import math
import re
import time
from collections.abc import Callable

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://pje-jurisprudencia.tjpb.jus.br"
SEARCH_URL = f"{BASE_URL}/api/jurisprudencia/pesquisar"
RESULTS_PER_PAGE = 10


TOKEN_RE = re.compile(r'<meta name="_token" content="([^"]+)"')


def fetch_csrf_token(request_fn: Callable[..., requests.Response]) -> str:
    """Fetch the ``_token`` CSRF value from the TJPB homepage meta tag.

    The Laravel backend embeds the token in ``<meta name="_token" ...>``.
    The token is then sent inside the JSON body of every search request
    (key ``_token``); no ``X-CSRF-TOKEN`` header is used.

    The GET is dispatched through ``request_fn`` so o cookie de sessao
    aterriza na ``requests.Session`` compartilhada pelo ``HTTPScraper``,
    e os POSTs subsequentes herdam o mesmo cookie automaticamente.
    """
    resp = request_fn("GET", BASE_URL, timeout=30)
    match = TOKEN_RE.search(resp.text)
    if not match:
        raise RuntimeError("Could not find CSRF token on TJPB page.")
    return match.group(1)


def build_cjsg_payload(
    token: str,
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
        "_token": token,
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
    request_fn: Callable[..., requests.Response],
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
        **kwargs: Additional filter parameters.
    """
    token = fetch_csrf_token(request_fn)
    headers = {"X-Requested-With": "XMLHttpRequest"}

    def _get_page(pagina_1based):
        payload = build_cjsg_payload(token, pesquisa, page=pagina_1based, **kwargs)
        resp = request_fn("POST", SEARCH_URL, json=payload, headers=headers, timeout=30)
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
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJPB"):
        resultados.append(_get_page(pagina_1based))
    return resultados
