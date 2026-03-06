"""
Functions for downloading specific to TJDFT
"""
import math

import requests


def cjsg_download(
    query,
    paginas=None,
    sinonimos=True,
    espelho=True,
    inteiro_teor=False,
    quantidade_por_pagina=10,
    base_url="https://jurisdf.tjdft.jus.br/api/v1/pesquisa",
):
    """
    Downloads raw results from the TJDFT jurisprudence search (using requests).
    Returns a list of raw results (JSON).

    Args:
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
    """
    headers = {"Content-Type": "application/json"}

    def _fetch_page(pagina):
        payload = {
            "query": query,
            "termosAcessorios": [],
            "pagina": pagina,
            "tamanho": quantidade_por_pagina,
            "sinonimos": sinonimos,
            "espelho": espelho,
            "inteiroTeor": inteiro_teor,
            "retornaInteiroTeor": False,
            "retornaTotalizacao": True,
        }
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
