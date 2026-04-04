"""
Parse raw results from the TJPA jurisprudence search.
"""
import pandas as pd


def _extract_nested(value, key="nome"):
    """Extract a value from a nested dict, or return the value as-is."""
    if isinstance(value, dict):
        return value.get(key)
    return value


def _extract_assuntos(assuntos):
    """Extract assunto names from the list of assunto dicts."""
    if not assuntos:
        return None
    if isinstance(assuntos, list):
        nomes = [a.get("nome", "") for a in assuntos if isinstance(a, dict)]
        return "; ".join(nomes) if nomes else None
    return assuntos


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """
    Extracts relevant data from the raw TJPA API responses.
    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw JSON responses from the TJPA API.
    """
    registros = []
    for response in resultados_brutos:
        content = response.get("data", {}).get("content", [])
        for item in content:
            registro = {
                "id": item.get("id"),
                "processo": item.get("numeroprocesso"),
                "tipo": item.get("tipo"),
                "area": item.get("area"),
                "origem": item.get("origem"),
                "classe": _extract_nested(item.get("classe")),
                "id_classe": _extract_nested(item.get("classe"), "codigo"),
                "assunto": _extract_assuntos(item.get("assuntos")),
                "id_assunto": item.get("idassunto"),
                "orgao_julgador": _extract_nested(item.get("orgaojulgador")),
                "orgao_julgador_colegiado": _extract_nested(item.get("orgaojulgadorcolegiado")),
                "competencia": _extract_nested(item.get("competencia")),
                "relator": (item.get("pessoas") or [None])[0],
                "data_julgamento": item.get("datajulgamento"),
                "data_documento": item.get("datadocumento"),
                "data_publicacao": item.get("datapublicacao"),
                "ementa": item.get("ementatextopuro"),
                "sentido_decisao": item.get("sentidodecisao"),
                "especie": item.get("especie"),
                "sistema_origem": _extract_nested(item.get("sistemaorigem")),
                "hash_storage": item.get("hashstorage"),
            }
            registros.append(registro)

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    for col in ["data_julgamento", "data_documento", "data_publicacao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce").dt.date

    # Order columns: main fields first
    principais = [
        "processo", "tipo", "classe", "assunto", "relator",
        "orgao_julgador_colegiado", "data_julgamento", "data_publicacao",
        "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]

    return df
