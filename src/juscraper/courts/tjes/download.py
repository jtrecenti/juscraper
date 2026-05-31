"""Downloads raw results from the TJES jurisprudence search."""
import time

from tqdm import tqdm

from juscraper.core.http import RequestFn

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
    *,
    request_fn: RequestFn,
) -> list:
    """Download raw JSON results from the TJES jurisprudence search.

    Returns a list of raw page responses (each containing ``docs``, ``total``,
    ``page``, ``per_page``, ``total_pages``). HTTP via ``request_fn`` (tipicamente
    ``TJESScraper._request_with_retry`` de ``core.http.HTTPScraper``), que
    centraliza retry exponencial para 429/5xx.
    """
    url = f"{BASE_URL}/search"
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

    def _get_page(pagina):
        params = _build_params(pagina=pagina, **common)
        # expect_json=True: o backend Solr do TJES devolve esporadicamente 200 com
        # corpo vazio; _request_with_retry retenta e, persistindo, levanta
        # EmptyResponseError com contexto em vez de JSONDecodeError opaco (#275).
        resp = request_fn("GET", url, params=params, timeout=30, expect_json=True)
        return resp.json()

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        total_pages = first.get("total_pages", 1)
        if total_pages > 1:
            for pag in tqdm(range(2, total_pages + 1), desc="Baixando paginas TJES"):
                time.sleep(1)
                resultados.append(_get_page(pag))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for i, pag in enumerate(tqdm(paginas_iter, desc="Baixando paginas TJES")):
        if i > 0:
            time.sleep(1)
        resultados.append(_get_page(pag))
    return resultados
