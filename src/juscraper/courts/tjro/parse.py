"""Parse raw results from the TJRO jurisprudence search (Elasticsearch)."""
import pandas as pd

from juscraper.core.parse_utils import clean_html, coerce_date_columns
from juscraper.utils.cnj import format_cnj


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJRO Elasticsearch responses.

    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw JSON responses from the TJRO API.
    """
    registros = []
    for response in resultados_brutos:
        hits = response.get("hits", {}).get("hits", [])
        for hit in hits:
            source = hit.get("_source", {})
            registros.append({
                "processo": source.get("nr_processo"),
                "tipo": source.get("tipo"),
                "classe": source.get("ds_classe_judicial"),
                "orgao_julgador": source.get("ds_orgao_julgador"),
                "orgao_julgador_colegiado": source.get("ds_orgao_julgador_colegiado"),
                "relator": source.get("ds_nome"),
                "assunto": source.get("ds_assunto_trf"),
                "data_julgamento": source.get("dtjulgamento"),
                "data_publicacao": source.get("dtpublicacao"),
                "grau_jurisdicao": source.get("grau_jurisdicao"),
                "sistema_origem": source.get("sistema_origem"),
                "ementa": clean_html(source.get("ds_modelo_documento")),
            })

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    coerce_date_columns(df, ["data_julgamento", "data_publicacao"])

    if "processo" in df.columns:
        df["processo"] = df["processo"].apply(lambda v: format_cnj(v, strict=False))

    principais = [
        "processo", "tipo", "classe", "orgao_julgador",
        "orgao_julgador_colegiado", "relator", "assunto",
        "data_julgamento", "data_publicacao", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]
    return df
