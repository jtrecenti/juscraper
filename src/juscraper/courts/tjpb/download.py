"""Downloads raw results from the TJPB jurisprudence search (Laravel API)."""
import math
from urllib.parse import unquote

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import baixar_paginas_pedidas

BASE_URL = "https://pje-jurisprudencia.tjpb.jus.br"
CLASSES_URL = f"{BASE_URL}/api/pje/classes/list"
SEARCH_URL = f"{BASE_URL}/api/jurisprudencia/pesquisar"
RESULTS_PER_PAGE = 10


def fetch_csrf_token(request_fn: RequestFn) -> str:
    """Obtém o cookie ``XSRF-TOKEN`` exigido pela API de pesquisa do TJPB.

    O GET vai à API de classes, que responde sem o desafio do Cloudflare
    que hoje bloqueia a home. Ele passa por ``request_fn`` para que os
    cookies ``XSRF-TOKEN`` e ``laravel_session`` fiquem na sessão
    compartilhada pelo ``HTTPScraper``; os POSTs seguintes herdam esses
    cookies e enviam o token decodificado no header ``X-XSRF-TOKEN``.
    """
    response = request_fn("GET", CLASSES_URL, perfil="classes")
    response.raise_for_status()
    token = response.cookies.get("XSRF-TOKEN")
    if not token:
        raise RuntimeError("Could not find XSRF-TOKEN cookie in TJPB API response.")
    return unquote(token)


def build_cjsg_payload(
    pesquisa: str,
    *,
    page: int = 1,
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
    xsrf_token = fetch_csrf_token(request_fn)
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
            perfil="cjsg",
        )
        data: dict = resp.json()
        return data

    def _n_pags(first: dict) -> int:
        total: int = first.get("total", 0)
        return math.ceil(total / RESULTS_PER_PAGE) if total else 1

    return baixar_paginas_pedidas(paginas, _get_page, _n_pags, tribunal="TJPB", sleep_time=1)
