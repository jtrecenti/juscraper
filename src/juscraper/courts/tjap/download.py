"""
Downloads raw results from the TJAP jurisprudence search (Tucujuris).
Uses requests library only (no browser automation needed).
"""
import json
import logging
import time

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://tucujuris.tjap.jus.br/api/publico/consultar-jurisprudencia"
SITE_URL = "https://tucujuris.tjap.jus.br"
FRONT_URL = SITE_URL + "/pages/consultar-jurisprudencia/consultar-jurisprudencia.html"
RESULTS_PER_PAGE = 20


def _build_payload(
    pesquisa: str,
    offset: int = 0,
    orgao: str = "0",
    numero_cnj: str | None = None,
    numero_acordao: str | None = None,
    numero_ano: str | None = None,
    palavras_exatas: bool = False,
    relator: str | None = None,
    secretaria: str | None = None,
    classe: str | None = None,
    votacao: str = "0",
    origem: str | None = None,
    tipo_jurisprudencia: str | None = None,
) -> dict:
    """Build the JSON payload for the TJAP search API."""
    payload = {
        "orgao": orgao,
        "ementa": pesquisa,
        "votacao": votacao,
        "tipo_jurisprudencia": tipo_jurisprudencia,
    }

    if offset > 0:
        payload["offset"] = offset
    if numero_cnj:
        payload["numeroCNJ"] = numero_cnj
    if numero_acordao:
        payload["numeroAcordao"] = numero_acordao
    if numero_ano:
        payload["numeroAno"] = numero_ano
    if palavras_exatas:
        payload["palavrasExatas"] = True
    if relator:
        payload["relator"] = relator
    if secretaria:
        payload["secretaria"] = secretaria
    if classe:
        payload["classe"] = classe
    if origem:
        payload["origem"] = origem

    return payload


def _fetch_page(session: requests.Session, payload: dict, max_retries: int = 3) -> dict:
    """Fetch a single page from the TJAP API with retry logic."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": FRONT_URL,
        "tucujuris-front-url": FRONT_URL,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, data=body, headers=headers, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJAP request failed (attempt %d/%d): %s. Retrying in %ds...",
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
    """Download raw results from the TJAP jurisprudence search (multiple pages).

    Returns a list of raw JSON responses (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
        session: Optional requests.Session to reuse.
        **kwargs: Additional parameters forwarded to ``_build_payload``.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def _get_page(pagina_1based):
        offset = (pagina_1based - 1) * RESULTS_PER_PAGE
        payload = _build_payload(pesquisa, offset=offset, **kwargs)
        data = _fetch_page(session, payload)
        time.sleep(1)
        return data

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        items = first.get("dados", [])
        if len(items) < RESULTS_PER_PAGE:
            return resultados

        page = 2
        while True:
            logger.info("TJAP: downloading page %d...", page)
            data = _get_page(page)
            resultados.append(data)
            items = data.get("dados", [])
            if len(items) < RESULTS_PER_PAGE:
                break
            page += 1
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJAP"):
        resultados.append(_get_page(pagina_1based))
    return resultados
