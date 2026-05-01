"""
Functions for downloading specific to TJDFT
"""
import math

import requests

BASE_URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"


def build_cjsg_payload(
    query: str,
    pagina: int,
    *,
    sinonimos: bool = True,
    espelho: bool = True,
    inteiro_teor: bool = False,
    quantidade_por_pagina: int = 10,
    termos_acessorios: list | None = None,
) -> dict:
    """Build the JSON payload sent to the TJDFT jurisprudence search API.

    Shared between the scraper and the offline capture script so both stay
    in sync with the API contract.
    """
    return {
        "query": query,
        "termosAcessorios": list(termos_acessorios) if termos_acessorios else [],
        "pagina": pagina,
        "tamanho": quantidade_por_pagina,
        "sinonimos": sinonimos,
        "espelho": espelho,
        "inteiroTeor": inteiro_teor,
        "retornaInteiroTeor": False,
        "retornaTotalizacao": True,
    }


def cjsg_download(
    query,
    paginas=None,
    sinonimos=True,
    espelho=True,
    inteiro_teor=False,
    quantidade_por_pagina=10,
    base_url=BASE_URL,
    data_julgamento_inicio=None,
    data_julgamento_fim=None,
    data_publicacao_inicio=None,
    data_publicacao_fim=None,
):
    """
    Downloads raw results from the TJDFT jurisprudence search (using requests).
    Returns a list of raw results (JSON).

    Args:
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
    """
    headers = {"Content-Type": "application/json"}

    termos_acessorios: list = []
    if data_julgamento_inicio and data_julgamento_fim:
        termos_acessorios.append(
            {"campo": "dataJulgamento", "valor": f"entre {data_julgamento_inicio} e {data_julgamento_fim}"}
        )
    if data_publicacao_inicio and data_publicacao_fim:
        termos_acessorios.append(
            {"campo": "dataPublicacao", "valor": f"entre {data_publicacao_inicio} e {data_publicacao_fim}"}
        )

    def _fetch_page(pagina):
        payload = build_cjsg_payload(
            query,
            pagina,
            sinonimos=sinonimos,
            espelho=espelho,
            inteiro_teor=inteiro_teor,
            quantidade_por_pagina=quantidade_por_pagina,
            termos_acessorios=termos_acessorios,
        )
        resp = requests.post(base_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    if paginas is None:
        resultados = []
        data = _fetch_page(1)
        registros = data.get("registros", [])
        resultados.extend(registros)
        total = data.get("total", len(registros))
        n_pags = math.ceil(total / quantidade_por_pagina) if total else 1
        for pagina in range(2, n_pags + 1):
            data = _fetch_page(pagina)
            resultados.extend(data.get("registros", []))
        return resultados

    resultados = []
    for pagina in paginas:
        data = _fetch_page(pagina)
        resultados.extend(data.get("registros", []))
    return resultados
