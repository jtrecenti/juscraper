"""
Funções de download específicas para TJDFT
"""
import requests

def cjsg_download(
    query,
    paginas=0,
    sinonimos=True,
    espelho=True,
    inteiro_teor=False,
    quantidade_por_pagina=10,
    base_url="https://jurisdf.tjdft.jus.br/api/v1/pesquisa",
):
    """
    Baixa resultados brutos da pesquisa de jurisprudência do TJDFT (usando requests).
    Retorna lista de resultados brutos (JSON).
    """
    resultados = []
    if isinstance(paginas, int):
        paginas_iter = range(1, paginas+1)
    else:
        paginas_iter = paginas
    for pagina in paginas_iter:
        payload = {
            "query": query,
            "termosAcessorios": [],
            "pagina": pagina,
            "tamanho": quantidade_por_pagina,
            "sinonimos": sinonimos,
            "espelho": espelho,
            "inteiroTeor": inteiro_teor,
            "retornaInteiroTeor": False,
            "retornaTotalizacao": True
        }
        headers = {
            "Content-Type": "application/json",
        }
        resp = requests.post(base_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        resultados.extend(data.get("registros", []))
    return resultados
