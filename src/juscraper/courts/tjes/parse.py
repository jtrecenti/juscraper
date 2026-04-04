"""
Parse raw results from the TJES jurisprudence search.
"""
import pandas as pd


# Fields to keep from each doc, in order of importance
_MAIN_FIELDS = [
    "nr_processo",
    "ementa",
    "magistrado",
    "orgao_julgador",
    "classe_judicial",
    "classe_judicial_sigla",
    "assunto_principal",
    "jurisdicao",
    "competencia",
    "dt_juntada",
]

_EXTRA_FIELDS = [
    "id",
    "acordao",
    "lista_assunto",
    "localizacao",
    "cargo_julgador",
    "cd_assunto_principal",
    "cd_classe_judicial",
    "id_assunto_principal",
    "id_classe_judicial",
    "id_jurisdicao",
    "id_localizacao",
    "id_cargo_julgador",
    "id_bin",
]


def cjsg_parse(resultados_brutos: list) -> pd.DataFrame:
    """
    Extract structured data from raw TJES search results.

    Parameters
    ----------
    resultados_brutos : list
        List of raw JSON responses from ``cjsg_download``.

    Returns
    -------
    pd.DataFrame
    """
    rows = []
    for page_data in resultados_brutos:
        docs = page_data.get("docs", [])
        for doc in docs:
            row = {}
            for field in _MAIN_FIELDS + _EXTRA_FIELDS:
                val = doc.get(field)
                # Flatten single-element lists (e.g. lista_assunto, localizacao)
                if isinstance(val, list):
                    val = "; ".join(str(v) for v in val) if val else None
                row[field] = val
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Convert date column
    if "dt_juntada" in df.columns:
        df["dt_juntada"] = pd.to_datetime(df["dt_juntada"], errors="coerce").dt.date

    # Reorder: main fields first
    present_main = [c for c in _MAIN_FIELDS if c in df.columns]
    present_extra = [c for c in df.columns if c not in _MAIN_FIELDS]
    df = df[present_main + present_extra]

    return df
