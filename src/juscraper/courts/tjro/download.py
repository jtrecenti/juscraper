"""Downloads raw results from the TJRO jurisprudence search (Elasticsearch API)."""
import logging
import math
import time
from typing import Optional

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://juris-back.tjro.jus.br/search/varios_parametros/"
RESULTS_PER_PAGE = 10


def build_cjsg_payload(
    pesquisa: str,
    offset: int = 0,
    size: int = RESULTS_PER_PAGE,
    tipo: list | None = None,
    nr_processo: str = "",
    relator: str = "",
    orgao_julgador: int | str = "",
    orgao_julgador_colegiado: int | str = "",
    classe: str = "",
    data_julgamento_inicio: str = "",
    data_julgamento_fim: str = "",
    instancia: list | None = None,
    termo_exato: bool = False,
) -> dict:
    """Build the JSON payload for the TJRO CJSG search API.

    Os parametros do helper usam os nomes canonicos do projeto
    (``relator``, ``classe``); o backend Elasticsearch continua recebendo
    seus proprios nomes (``ds_nome``, ``ds_classe_judicial``) no JSON.
    """
    if tipo is None:
        tipo = ["EMENTA"]

    fields: dict = {"tipo": tipo, "query": pesquisa}
    if nr_processo:
        fields["nr_processo"] = nr_processo
    if relator:
        fields["ds_nome"] = relator
    if orgao_julgador:
        fields["id_orgao_julgador"] = str(orgao_julgador)
    if orgao_julgador_colegiado:
        fields["id_orgao_julgador_colegiado"] = str(orgao_julgador_colegiado)
    if classe:
        fields["ds_classe_judicial"] = classe
    if data_julgamento_inicio:
        fields["dtjulgamento_inicio"] = data_julgamento_inicio
    if data_julgamento_fim:
        fields["dtjulgamento_fim"] = data_julgamento_fim
    if instancia:
        fields["grau_jurisdicao"] = instancia
    if termo_exato:
        fields["termoExato"] = True

    return {
        "from": offset,
        "size": size,
        "fields": fields,
        "sort": [{"_score": "desc"}, {"dtjulgamento": "desc"}],
        "token": "",
        "highlight": {
            "type": "plain",
            "number_of_fragments": 1,
            "fragment_size": 3000,
            "require_field_match": "true",
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "fields": [{"ds_modelo_documento": {"number_of_fragments": 1}}],
        },
    }


def _fetch_page(session: requests.Session, payload: dict, max_retries: int = 3) -> dict:
    """Fetch a single page from the TJRO API with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, json=payload, timeout=30)
            resp.raise_for_status()
            data: dict = resp.json()
            return data
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJRO request failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return {}  # unreachable


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> list:
    """Download raw results from the TJRO jurisprudence search.

    Returns a list of raw JSON responses (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        session: Optional requests.Session to reuse.
        **kwargs: Additional filter parameters forwarded to ``build_cjsg_payload``.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def _get_page(pagina_1based):
        offset = (pagina_1based - 1) * RESULTS_PER_PAGE
        payload = build_cjsg_payload(pesquisa, offset=offset, **kwargs)
        data = _fetch_page(session, payload)
        time.sleep(1)
        return data

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        total_info = first.get("hits", {}).get("total", {})
        total = total_info.get("value", 0) if isinstance(total_info, dict) else total_info
        n_pags = math.ceil(total / RESULTS_PER_PAGE) if total else 1
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJRO"):
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJRO"):
        resultados.append(_get_page(pagina_1based))
    return resultados
