"""
Parse raw results from the TJBA jurisprudence search.
"""
import pandas as pd


def cjsg_parse(resultados_brutos: list) -> pd.DataFrame:
    """
    Extract structured data from TJBA raw GraphQL responses.

    Parameters
    ----------
    resultados_brutos : list
        List of raw response dicts as returned by ``cjsg_download``.

    Returns
    -------
    pd.DataFrame
        DataFrame with one row per decision.
    """
    rows = []
    for page_data in resultados_brutos:
        decisoes = (
            page_data.get("data", {}).get("filter", {}).get("decisoes", [])
        )
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
                "ementa": d.get("ementa"),
                "hash": d.get("hash"),
            })

    df = pd.DataFrame(rows)
    if "data_publicacao" in df.columns:
        df["data_publicacao"] = pd.to_datetime(
            df["data_publicacao"], errors="coerce"
        ).dt.date
    principais = [
        "processo", "relator", "orgao_julgador", "classe",
        "tipo_decisao", "data_publicacao", "ementa", "hash",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_extras = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_extras]
    return df
