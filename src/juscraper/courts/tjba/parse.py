"""
Parse raw results from the TJBA jurisprudence search.
"""
import pandas as pd

from juscraper.core.parse_utils import coerce_date_columns, normalizar_texto


def cjsg_parse(resultados_brutos: list) -> pd.DataFrame:
    """Extrai os dados estruturados das respostas GraphQL brutas do TJBA.

    Args:
        resultados_brutos: Lista dos dicionários da resposta, como devolvidos
            por ``cjsg_download``.

    Returns:
        Uma linha por decisão.
    """
    rows = []
    for page_data in resultados_brutos:
        # Defensive chain: TJBA's GraphQL can legitimately return ``null`` for
        # any intermediate container when a search hits zero results, mirroring
        # what TJMT does with ``AcordaoCollection: null``. ``.get(key, {})`` only
        # covers the missing-key case; ``or {}`` also normalizes explicit nulls.
        data = page_data.get("data") or {}
        filter_ = data.get("filter") or {}
        decisoes = filter_.get("decisoes") or []
        for d in decisoes:
            relator = d.get("relator") or {}
            orgao = d.get("orgaoJulgador") or {}
            classe = d.get("classe") or {}
            rows.append({
                "processo": d.get("numeroProcesso"),
                "relator": relator.get("nome"),
                "relator_id": relator.get("id"),
                "orgao_julgador": orgao.get("nome"),
                "orgao_julgador_id": orgao.get("id"),
                "classe": classe.get("descricao"),
                "classe_id": classe.get("id"),
                "tipo_decisao": d.get("tipoDecisao"),
                "data_publicacao": d.get("dataPublicacao"),
                "ementa": normalizar_texto(d.get("ementa")),
                "hash": d.get("hash"),
            })

    df = pd.DataFrame(rows)
    coerce_date_columns(df, ["data_publicacao"])
    principais = [
        "processo", "relator", "orgao_julgador", "classe",
        "tipo_decisao", "data_publicacao", "ementa", "hash",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_extras = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_extras]
    return df
