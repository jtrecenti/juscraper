"""
Parse raw results from the TJAP jurisprudence search (Tucujuris).
"""
import re

import pandas as pd


def _clean_html(html_text: str | None) -> str | None:
    """Remove HTML tags and decode HTML entities from ementa text."""
    if not html_text:
        return html_text
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", html_text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&apos;", "'")
    text = text.replace("&nbsp;", " ")
    # Decode accented character entities (e.g., &Aacute; -> Á)
    text = re.sub(
        r"&([A-Za-z]+(?:acute|grave|circ|tilde|uml|cedil|ring|slash|lig));",
        lambda m: _decode_entity(m.group(0)),
        text,
    )
    # Decode numeric entities
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _decode_entity(entity: str) -> str:
    """Decode a named HTML entity using html module."""
    import html
    try:
        return html.unescape(entity)
    except Exception:
        return entity


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
                "ementa": _clean_html(item.get("ementa")),
            }
            registros.append(registro)

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    for col in ["data_julgamento", "data_publicacao", "data_registro"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce").dt.date

    # Order columns: main fields first
    principais = [
        "processo", "numero_acordao", "classe", "relator", "lotacao",
        "comarca", "votacao", "data_julgamento", "data_publicacao", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]

    return df
