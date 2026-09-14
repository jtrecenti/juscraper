"""Conversao das respostas da API de jurisprudencia do STF em linhas."""
from __future__ import annotations

# Chaves do ``_source`` renomeadas para os nomes canonicos do projeto. As demais
# (``decisao_texto``, ``inteiro_teor_url``, ``base``, ``orgao_julgador``,
# ``ministro_facet``, ``partes_lista_texto``...) passam como vem da API.
_RENOMEAR = {
    "processo_codigo_completo": "processo",
    "processo_classe_processual_unificada_classe_sigla": "classe",
    "relator_processo_nome": "relator",
    "ementa_texto": "ementa",
    "julgamento_data": "data_julgamento",
    "publicacao_data": "data_publicacao",
}


def parse_decisoes(respostas: list[dict]) -> list[dict]:
    """Uma linha por documento das respostas de busca, com as chaves de :data:`_RENOMEAR` renomeadas."""
    return [
        {_RENOMEAR.get(chave, chave): valor for chave, valor in hit["_source"].items()}
        for resposta in respostas
        for hit in resposta["result"]["hits"]["hits"]
    ]


def parse_contagem(resposta: dict) -> list[dict]:
    """Linhas ``faceta``, ``valor``, ``n``: o total e cada bucket das agregacoes.

    As agregacoes de faceta (ministro, classe, UF, orgao) vem aninhadas num filtro,
    ``{"doc_count", "<nome>": {"buckets": [{"key", "doc_count"}]}}``. As de base e dos
    indicadores booleanos vem como ``filters``, ``{"buckets": {"<chave>": {"doc_count"}}}``.
    """
    resultado = resposta["result"]
    linhas: list[dict] = [{"faceta": "total", "valor": None, "n": resultado["hits"]["total"]["value"]}]
    for nome, agg in resultado.get("aggregations", {}).items():
        buckets = agg.get(nome, agg)["buckets"]
        if isinstance(buckets, dict):
            pares = [(chave, bucket["doc_count"]) for chave, bucket in buckets.items()]
        else:
            pares = [(bucket["key"], bucket["doc_count"]) for bucket in buckets]
        faceta = nome.removesuffix("_agg")
        linhas.extend({"faceta": faceta, "valor": valor, "n": n} for valor, n in pares)
    return linhas
