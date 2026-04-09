"""Parse raw results from the TJPB jurisprudence search."""
import pandas as pd


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJPB API responses.

    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw JSON responses from the TJPB API.
    """
    registros = []
    for response in resultados_brutos:
        hits = response.get("hits", [])
        for hit in hits:
            registros.append({
                "processo": hit.get("numero_processo"),
                "ementa": hit.get("ementa"),
                "data_julgamento": hit.get("dt_ementa"),
            })

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    if "data_julgamento" in df.columns:
        df["data_julgamento"] = pd.to_datetime(
            df["data_julgamento"], format="%d/%m/%Y", errors="coerce"
        ).dt.date

    return df
