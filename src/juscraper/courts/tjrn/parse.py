"""Parse raw results from the TJRN jurisprudence search (Elasticsearch)."""
import re

import pandas as pd


def _clean_html(html_text: str | None) -> str | None:
    """Remove HTML tags from text."""
    if not html_text:
        return html_text
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
                "ementa": _clean_html(source.get("ementa")),
            })

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    for col in ["data_julgamento", "data_publicacao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # Format processo as CNJ pattern
    if "processo" in df.columns:
        df["processo"] = df["processo"].apply(_format_cnj)

    principais = [
        "processo", "classe", "orgao_julgador", "colegiado",
        "relator", "tipo_decisao", "data_julgamento", "data_publicacao",
        "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]
    return df


def _format_cnj(numero: str | None) -> str | None:
    """Format a raw 20-digit number as CNJ pattern NNNNNNN-DD.YYYY.J.TR.OOOO."""
    if not numero or not numero.isdigit() or len(numero) != 20:
        return numero
    return (
        f"{numero[:7]}-{numero[7:9]}.{numero[9:13]}."
        f"{numero[13]}.{numero[14:16]}.{numero[16:]}"
    )
