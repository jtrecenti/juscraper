"""
Downloads raw results from the TJPA jurisprudence search.
"""
import json
import logging
import time
from typing import Optional

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.tjpa.jus.br/bff/api/decisoes/buscar"
SITE_URL = "https://jurisprudencia.tjpa.jus.br"
RESULTS_PER_PAGE = 25

CJSG_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Referer": SITE_URL + "/",
    "Origin": SITE_URL,
}


def build_cjsg_payload(
    pesquisa: str,
    pagina_0based: int,
    size: int = RESULTS_PER_PAGE,
    origem: Optional[list] = None,
    tipo: Optional[list] = None,
    relator: Optional[str] = None,
    orgao_julgador_colegiado: Optional[str] = None,
    classe: Optional[str] = None,
    assunto: Optional[str] = None,
    data_julgamento_inicio: Optional[str] = None,
    data_julgamento_fim: Optional[str] = None,
    data_publicacao_inicio: Optional[str] = None,
    data_publicacao_fim: Optional[str] = None,
    sort_by: str = "datajulgamento",
    sort_order: str = "desc",
    query_type: str = "free",
    query_scope: str = "ementa",
) -> dict:
    """Build the JSON payload for the TJPA search API."""
    if origem is None:
        origem = ["tribunal de justiça do estado do pará"]
    if tipo is None:
        tipo = ["acórdão", "decisão monocrática"]

    payload = {
        "query": pesquisa,
        "queryType": query_type,
        "queryScope": query_scope,
        "origem": origem,
        "tipo": tipo,
        "page": pagina_0based,
        "size": size,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }

    if relator:
        payload["relator"] = relator
    if orgao_julgador_colegiado:
        payload["orgaoJulgadorColegiado"] = orgao_julgador_colegiado
    if classe:
        payload["classe"] = classe
    if assunto:
        payload["assunto"] = assunto
    if data_julgamento_inicio:
        payload["dataJulgamentoInicio"] = data_julgamento_inicio
    if data_julgamento_fim:
        payload["dataJulgamentoFim"] = data_julgamento_fim
    if data_publicacao_inicio:
        payload["dataPublicacaoInicio"] = data_publicacao_inicio
    if data_publicacao_fim:
        payload["dataPublicacaoFim"] = data_publicacao_fim

    return payload


def _fetch_page(session: requests.Session, payload: dict, max_retries: int = 3) -> dict:
    """Fetch a single page from the TJPA API with retry logic."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, data=body, headers=CJSG_HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            data: dict = resp.json()
            return data
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning("TJPA request failed (attempt %d/%d): %s. Retrying in %ds...",
                           attempt, max_retries, exc, wait)
            time.sleep(wait)
    return {}  # unreachable


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> list:
    """
    Downloads raw results from the TJPA jurisprudence search (multiple pages).
    Returns a list of raw JSON responses.

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
        session: Optional requests.Session to reuse.
        **kwargs: Additional parameters forwarded to ``build_cjsg_payload``.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def _get_page(pagina_1based):
        payload = build_cjsg_payload(pesquisa, pagina_0based=pagina_1based - 1, **kwargs)
        data = _fetch_page(session, payload)
        time.sleep(1)
        return data

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        total_pages = first.get("data", {}).get("totalPages", 1)
        if total_pages > 1:
            logger.info("TJPA: %d pages found. Downloading all...", total_pages)
            for pagina in tqdm(range(2, total_pages + 1), desc="Baixando páginas TJPA"):
                resultados.append(_get_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando páginas TJPA"):
        resultados.append(_get_page(pagina_1based))
    return resultados
