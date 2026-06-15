"""Parse raw results from the TJAP jurisprudence search (Tucujuris)."""
import pandas as pd

from juscraper.core.parse_utils import clean_html, coerce_date_columns


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJAP API responses.

    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw JSON responses from the TJAP API.
    """
    registros = []
    for response in resultados_brutos:
        items = response.get("dados", [])
        if not isinstance(items, list):
            continue
        for item in items:
            registro = {
                "id": item.get("id"),
                "identificador": item.get("identificador"),
                "processo": item.get("numeroano"),
                "numero_acordao": item.get("numeroacordao"),
                "classe": item.get("classe"),
                "relator": item.get("nomerelator"),
                "lotacao": item.get("lotacao"),
                "comarca": item.get("comarca"),
                "votacao": item.get("votacao"),
                "data_julgamento": item.get("datajulgamento"),
                "data_publicacao": item.get("datapublicacao"),
                "data_registro": item.get("dataregistro"),
                "ementa": clean_html(item.get("ementa")),
            }
            registros.append(registro)

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    coerce_date_columns(df, ["data_julgamento", "data_publicacao", "data_registro"])

    principais = [
        "processo", "numero_acordao", "classe", "relator", "lotacao",
        "comarca", "votacao", "data_julgamento", "data_publicacao", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]

    return df
