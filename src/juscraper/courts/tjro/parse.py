"""Parse raw results from the TJRO jurisprudence search (Elasticsearch)."""
import re

import pandas as pd


def _clean_html(html_text: str | None) -> str | None:
    """Remove HTML tags from text."""
    if not html_text:
        return html_text
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _format_cnj(numero: str | None) -> str | None:
    """Format a raw 20-digit number as CNJ pattern NNNNNNN-DD.YYYY.J.TR.OOOO."""
    if not numero or not numero.isdigit() or len(numero) != 20:
        return numero
    return (
        f"{numero[:7]}-{numero[7:9]}.{numero[9:13]}."
        f"{numero[13]}.{numero[14:16]}.{numero[16:]}"
    )


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
                "ementa": _clean_html(source.get("ds_modelo_documento")),
            })

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    for col in ["data_julgamento", "data_publicacao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    if "processo" in df.columns:
        df["processo"] = df["processo"].apply(_format_cnj)

    principais = [
        "processo", "tipo", "classe", "orgao_julgador",
        "orgao_julgador_colegiado", "relator", "assunto",
        "data_julgamento", "data_publicacao", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]
    return df
