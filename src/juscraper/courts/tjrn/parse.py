"""Parse raw results from the TJRN jurisprudence search (Elasticsearch)."""
import pandas as pd

from juscraper.core.parse_utils import coerce_date_columns, html_para_texto
from juscraper.utils.cnj import format_cnj

# Colunas na ordem do DataFrame, para a busca sem resultado também as trazer.
_COLUNAS = [
    "processo", "classe", "orgao_julgador", "colegiado",
    "relator", "tipo_decisao", "data_julgamento", "data_publicacao",
    "ementa", "sistema", "sigiloso",
]


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJRN Elasticsearch responses.

    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw JSON responses from the TJRN API.
    """
    registros = []
    for response in resultados_brutos:
        hits = response.get("hits", {}).get("hits", [])
        for hit in hits:
            source = hit.get("_source", {})
            registros.append({
                "processo": source.get("numero_processo"),
                "classe": source.get("classe_judicial"),
                "orgao_julgador": source.get("orgao_julgador"),
                "colegiado": source.get("colegiado"),
                "relator": source.get("relator"),
                "tipo_decisao": source.get("tipo_decisao"),
                "data_julgamento": (
                    source.get("dt_assinatura_teor")
                    or source.get("dt_assinatura_ementa")
                ),
                "data_publicacao": source.get("dt_publicacao"),
                "sistema": source.get("sistema"),
                "sigiloso": source.get("sigiloso"),
                "ementa": html_para_texto(source.get("ementa")),
            })

    df = pd.DataFrame(registros, columns=_COLUNAS)
    if df.empty:
        return df

    coerce_date_columns(df, ["data_julgamento", "data_publicacao"])

    if "processo" in df.columns:
        df["processo"] = df["processo"].apply(lambda v: format_cnj(v, strict=False))

    return df
