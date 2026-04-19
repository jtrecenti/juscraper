"""
Functions for downloading specific to TJDFT
"""
import math

import requests

from juscraper.utils.params import to_iso_date


def cjsg_download(
    query,
    paginas=None,
    sinonimos=True,
    espelho=True,
    inteiro_teor=False,
    quantidade_por_pagina=10,
    base_url="https://jurisdf.tjdft.jus.br/api/v1/pesquisa",
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

    termos_acessorios = []
    jul_ini = to_iso_date(data_julgamento_inicio)
    jul_fim = to_iso_date(data_julgamento_fim)
    if jul_ini and jul_fim:
        termos_acessorios.append(
            {"campo": "dataJulgamento", "valor": f"entre {jul_ini} e {jul_fim}"}
        )
    pub_ini = to_iso_date(data_publicacao_inicio)
    pub_fim = to_iso_date(data_publicacao_fim)
    if pub_ini and pub_fim:
        termos_acessorios.append(
            {"campo": "dataPublicacao", "valor": f"entre {pub_ini} e {pub_fim}"}
        )

    def _fetch_page(pagina):
        payload = {
            "query": query,
            "termosAcessorios": termos_acessorios,
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
