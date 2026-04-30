"""
Downloads raw pages from the TJTO jurisprudence search.
"""
import logging
import math
import re
import time
from typing import Any, Dict, Optional

import requests
from tqdm import tqdm

from juscraper.utils.params import to_br_date

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.tjto.jus.br/consulta.php"
EMENTA_URL = "https://jurisprudencia.tjto.jus.br/ementa.php"
RESULTS_PER_PAGE = 20

# type_minuta_selected: 1 = Acórdãos, 2 = Decisões Monocráticas, 3 = Sentenças
TYPE_MINUTA_MAP = {
    "acordaos": "1",
    "decisoes": "2",
    "sentencas": "3",
}


def _get_total_results(html: str) -> int:
    """Extract the total number of results from the active tab's count."""
    match = re.search(r'active\s*"[^>]*>[^<]*<span[^>]*>\(([0-9.]+)\)', html)
    if match:
        return int(match.group(1).replace(".", ""))
    match = re.search(r'\((\d[\d.]*)\s*resultados?\)', html)
    if match:
        return int(match.group(1).replace(".", ""))
    return 0


def build_cjsg_payload(
    termo: str,
    start: int = 0,
    *,
    type_minuta: str = "1",
    tip_criterio_inst: str = "",
    tip_criterio_data: str = "DESC",
    numero_processo: str = "",
    dat_jul_ini: str = "",
    dat_jul_fim: str = "",
    soementa: bool = False,
) -> dict:
    """Build the form-encoded body for the TJTO jurisprudence search.

    ``start`` is a 0-based Solr offset (page = ``start // RESULTS_PER_PAGE + 1``).
    The backend only applies ``dat_jul_ini``/``dat_jul_fim`` when
    ``tempo_julgados="pers"`` (the "Intervalo personalizado" option in the UI);
    an empty value silently falls back to "all dates".
    """
    dat_ini_br = to_br_date(dat_jul_ini) or ""
    dat_fim_br = to_br_date(dat_jul_fim) or ""
    tempo_julgados = "pers" if (dat_ini_br or dat_fim_br) else ""
    payload: Dict[str, str] = {
        "start": str(start),
        "rows": str(RESULTS_PER_PAGE),
        "type_minuta_selected": type_minuta,
        "q": termo,
        "tip_criterio_inst": tip_criterio_inst,
        "tip_criterio_data": tip_criterio_data,
        "numero_processo": numero_processo,
        "tempo_julgados": tempo_julgados,
        "dat_jul_ini": dat_ini_br,
        "dat_jul_fim": dat_fim_br,
    }
    if soementa:
        payload["soementa"] = "on"
    return payload


def _fetch_page(
    session: requests.Session,
    termo: str,
    start: int,
    type_minuta: str = "1",
    tip_criterio_inst: str = "",
    tip_criterio_data: str = "DESC",
    numero_processo: str = "",
    dat_jul_ini: str = "",
    dat_jul_fim: str = "",
    soementa: bool = False,
    max_retries: int = 3,
) -> str:
    """Fetch a single page of results from the TJTO jurisprudence search."""
    payload = build_cjsg_payload(
        termo=termo,
        start=start,
        type_minuta=type_minuta,
        tip_criterio_inst=tip_criterio_inst,
        tip_criterio_data=tip_criterio_data,
        numero_processo=numero_processo,
        dat_jul_ini=dat_jul_ini,
        dat_jul_fim=dat_jul_fim,
        soementa=soementa,
    )

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, data=payload, timeout=60)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJTO request failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return ""  # unreachable


def _fetch_ementa(session: requests.Session, uuid: str) -> Dict[Any, Any]:
    """Fetch ementa JSON for a given document UUID."""
    resp = session.get(EMENTA_URL, params={"id": uuid}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    docs = data.get("response", {}).get("docs", [])
    doc: Dict[Any, Any] = docs[0] if docs else {}
    return doc


def cjsg_download_manager(
    termo: str,
    paginas=None,
    type_minuta: str = "1",
    tip_criterio_inst: str = "",
    tip_criterio_data: str = "DESC",
    numero_processo: str = "",
    dat_jul_ini: str = "",
    dat_jul_fim: str = "",
    soementa: bool = False,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> list:
    """Download raw HTML pages from TJTO jurisprudence search.

    Args:
        termo: Search term.
        paginas: Pages to download (1-based). None = all.
        type_minuta: '1' (Acórdãos), '2' (Decisões Monocráticas), '3' (Sentenças).

    Returns:
        List of raw HTML strings, one per page.
    """
    if session is None:
        session = requests.Session()

    fetch_kwargs: Dict[str, Any] = {
        "type_minuta": type_minuta,
        "tip_criterio_inst": tip_criterio_inst,
        "tip_criterio_data": tip_criterio_data,
        "numero_processo": numero_processo,
        "dat_jul_ini": dat_jul_ini,
        "dat_jul_fim": dat_jul_fim,
        "soementa": soementa,
    }

    if paginas is None:
        first_html = _fetch_page(session, termo, start=0, **fetch_kwargs)
        resultados = [first_html]
        total = _get_total_results(first_html)
        n_pages = math.ceil(total / RESULTS_PER_PAGE) if total else 1
        if n_pages > 1:
            for page_num in tqdm(range(2, n_pages + 1), desc="Baixando páginas TJTO"):
                time.sleep(1)
                start = (page_num - 1) * RESULTS_PER_PAGE
                resultados.append(_fetch_page(session, termo, start=start, **fetch_kwargs))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for page_num in tqdm(paginas_iter, desc="Baixando páginas TJTO"):
        if resultados:
            time.sleep(1)
        start = (page_num - 1) * RESULTS_PER_PAGE
        resultados.append(_fetch_page(session, termo, start=start, **fetch_kwargs))
    return resultados
