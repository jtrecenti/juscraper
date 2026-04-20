"""
Downloads raw results from the TJMT jurisprudence search.
"""
import logging
import math
import time

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

CONFIG_URL = "https://jurisprudencia.tjmt.jus.br/assets/config/config.json"
DEFAULT_PAGE_SIZE = 10


def _get_api_config(session: requests.Session) -> dict:
    """Fetch the public config.json to obtain the API URL and token."""
    resp = session.get(CONFIG_URL, timeout=30)
    resp.raise_for_status()
    cfg = resp.json()
    return {
        "api_url": cfg["api_url"],
        "token": cfg["api_hellsgate_token"],
    }


def _build_params(
    pesquisa: str,
    pagina: int,
    quantidade: int,
    tipo_consulta: str,
    data_julgamento_inicio: str | None,
    data_julgamento_fim: str | None,
    relator: str | None,
    orgao_julgador: str | None,
    classe: str | None,
    tipo_processo: str | None,
    thesaurus: bool,
) -> dict:
    """Build the query-string parameters for the Consulta endpoint."""
    if classe:
        raise NotImplementedError(
            "O filtro 'classe' foi recebido, mas não é suportado por esta "
            "implementação do endpoint de consulta do TJMT."
        )
    return {
        "filtro.isBasica": "true",
        "filtro.indicePagina": pagina,
        "filtro.quantidadePagina": quantidade,
        "filtro.tipoConsulta": tipo_consulta,
        "filtro.termoDeBusca": pesquisa,
        "filtro.area": "",
        "filtro.numeroProtocolo": "",
        "filtro.periodoDataDe": data_julgamento_inicio or "",
        "filtro.periodoDataAte": data_julgamento_fim or "",
        "filtro.tipoBusca": "1",
        "filtro.relator": relator or "",
        "filtro.julgamento": "",
        "filtro.orgaoJulgador": orgao_julgador or "",
        "filtro.colegiado": "",
        "filtro.localConsultaAcordao": "",
        "filtro.fqOrgaoJulgador": "",
        "filtro.fqTipoProcesso": "",
        "filtro.fqRelator": "",
        "filtro.fqJulgamento": "",
        "filtro.fqAssunto": "",
        "filtro.ordenacao.ordenarPor": "DataDecrescente",
        "filtro.ordenacao.ordenarDataPor": "Julgamento",
        "filtro.tipoProcesso": tipo_processo or "",
        "filtro.thesaurus": str(thesaurus).lower(),
        "filtro.fqTermos": "",
    }


def _to_tjmt_date(date_str: str | None) -> str | None:
    """Convert a date string from yyyy-mm-dd to dd/mm/yyyy (TJMT format)."""
    if not date_str:
        return None
    parts = date_str.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return date_str


def cjsg_download(
    pesquisa: str,
    paginas=None,
    tipo_consulta: str = "Acordao",
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    relator: str | None = None,
    orgao_julgador: str | None = None,
    classe: str | None = None,
    tipo_processo: str | None = None,
    thesaurus: bool = False,
    quantidade_por_pagina: int = DEFAULT_PAGE_SIZE,
    session: requests.Session | None = None,
) -> list:
    """Download raw JSON results from the TJMT jurisprudence API.

    Args:
        pesquisa: Search term.
        paginas: Pages to download (1-based). ``None`` fetches all.
        tipo_consulta: ``"Acordao"`` or ``"DecisaoMonocratica"``.
        data_julgamento_inicio: Start date (``yyyy-mm-dd`` or ``dd/mm/yyyy``).
        data_julgamento_fim: End date (``yyyy-mm-dd`` or ``dd/mm/yyyy``).
        relator: Filter by judge name.
        orgao_julgador: Filter by court chamber.
        classe: Filter by case class.
        tipo_processo: ``"Cível"`` or ``"Criminal"``.
        thesaurus: Whether to use synonym search.
        quantidade_por_pagina: Items per page (default 10).
        session: Optional ``requests.Session`` to reuse.

    Returns:
        List of raw JSON response dicts, one per page.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    cfg = _get_api_config(session)
    api_url = cfg["api_url"]
    token = cfg["token"]

    session.headers.update({
        "Token": token,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://jurisprudencia.tjmt.jus.br/",
    })

    data_inicio_fmt = _to_tjmt_date(data_julgamento_inicio)
    data_fim_fmt = _to_tjmt_date(data_julgamento_fim)

    def _fetch_page(pagina: int) -> dict:
        params = _build_params(
            pesquisa=pesquisa,
            pagina=pagina,
            quantidade=quantidade_por_pagina,
            tipo_consulta=tipo_consulta,
            data_julgamento_inicio=data_inicio_fmt,
            data_julgamento_fim=data_fim_fmt,
            relator=relator,
            orgao_julgador=orgao_julgador,
            classe=classe,
            tipo_processo=tipo_processo,
            thesaurus=thesaurus,
        )
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = session.get(f"{api_url}/api/Consulta", params=params, timeout=60)
                resp.raise_for_status()
                data: dict = resp.json()
                return data
            except requests.RequestException:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** (attempt + 1)
                logger.warning("Request failed (attempt %d/%d), retrying in %ds...", attempt + 1, max_retries, wait)
                time.sleep(wait)
        raise RuntimeError("unreachable")  # satisfaz o mypy; loop acima sempre retorna ou levanta

    collection_key = "AcordaoCollection" if tipo_consulta == "Acordao" else "DecisaoMonocraticaCollection"
    count_key = "CountAcordaoDocumento" if tipo_consulta == "Acordao" else "CountDecisaoMonocratica"

    if paginas is None:
        first = _fetch_page(1)
        resultados = [first]
        total = first.get(count_key, 0)
        n_pags = math.ceil(total / quantidade_por_pagina) if total else 1
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando páginas TJMT"):
                resultados.append(_fetch_page(pagina))
                time.sleep(1)
        return resultados

    paginas_list = list(paginas)
    resultados = []
    for pagina in tqdm(paginas_list, desc="Baixando páginas TJMT"):
        resultados.append(_fetch_page(pagina))
        if len(paginas_list) > 1:
            time.sleep(1)
    return resultados
