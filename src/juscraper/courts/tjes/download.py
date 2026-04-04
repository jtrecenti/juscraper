"""
Downloads raw results from the TJES jurisprudence search.
"""
import logging
import time

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://sistemas.tjes.jus.br/consulta-jurisprudencia/api"

# Maps tab names used in the UI to core identifiers in the API
CORES = {
    "pje1g": "pje1g",
    "pje2g": "pje2g",
    "pje2g_mono": "pje2g_mono",
    "legado": "legado",
    "turma_recursal_legado": "turma_recursal_legado",
}

DEFAULT_CORE = "pje2g"
CJSG_CORES = {"pje2g", "pje2g_mono", "legado", "turma_recursal_legado"}
CJPG_CORE = "pje1g"
DEFAULT_PER_PAGE = 20
MAX_RETRIES = 3
RETRY_BACKOFF = 2


def _build_params(
    pesquisa,
    pagina,
    per_page,
    core,
    busca_exata,
    data_inicio,
    data_fim,
    magistrado,
    orgao_julgador,
    classe_judicial,
    jurisdicao,
    assunto,
    ordenacao,
):
    """Build the query-string parameters for the search endpoint."""
    params = {
        "core": core,
        "q": pesquisa or "*",
        "page": pagina,
        "per_page": per_page,
    }
    if busca_exata:
        params["exact_match"] = "true"
    if data_inicio:
        params["dataIni"] = data_inicio
    if data_fim:
        params["dataFim"] = data_fim
    if magistrado:
        params["magistrado"] = magistrado
    if orgao_julgador:
        params["orgao_julgador"] = orgao_julgador
    if classe_judicial:
        params["classe_judicial"] = classe_judicial
    if jurisdicao:
        params["jurisdicao"] = jurisdicao
    if assunto:
        params["lista_assunto"] = assunto
    if ordenacao:
        params["sort"] = ordenacao
    return params


def _fetch_page(session, params):
    """Fetch a single page with retry logic."""
    url = f"{BASE_URL}/search"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF ** attempt
            logger.warning(
                "TJES request failed (attempt %d/%d): %s — retrying in %ds",
                attempt, MAX_RETRIES, exc, wait,
            )
            time.sleep(wait)
    return {}  # unreachable, but keeps linters happy


def cjsg_download(
    pesquisa=None,
    paginas=None,
    core=DEFAULT_CORE,
    busca_exata=False,
    data_inicio=None,
    data_fim=None,
    magistrado=None,
    orgao_julgador=None,
    classe_judicial=None,
    jurisdicao=None,
    assunto=None,
    ordenacao=None,
    per_page=DEFAULT_PER_PAGE,
    session=None,
) -> list:
    """
    Download raw JSON results from the TJES jurisprudence search.

    Returns a list of raw page responses (each containing ``docs``, ``total``,
    ``page``, ``per_page``, ``total_pages``).
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    common = dict(
        pesquisa=pesquisa,
        per_page=per_page,
        core=core,
        busca_exata=busca_exata,
        data_inicio=data_inicio,
        data_fim=data_fim,
        magistrado=magistrado,
        orgao_julgador=orgao_julgador,
        classe_judicial=classe_judicial,
        jurisdicao=jurisdicao,
        assunto=assunto,
        ordenacao=ordenacao,
    )

    if paginas is None:
        # Fetch first page to discover total
        params = _build_params(pagina=1, **common)
        first = _fetch_page(session, params)
        resultados = [first]
        total_pages = first.get("total_pages", 1)
        if total_pages > 1:
            for pag in tqdm(range(2, total_pages + 1), desc="Baixando paginas TJES"):
                time.sleep(1)
                params = _build_params(pagina=pag, **common)
                resultados.append(_fetch_page(session, params))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for i, pag in enumerate(tqdm(paginas_iter, desc="Baixando paginas TJES")):
        if i > 0:
            time.sleep(1)
        params = _build_params(pagina=pag, **common)
        resultados.append(_fetch_page(session, params))
    return resultados
