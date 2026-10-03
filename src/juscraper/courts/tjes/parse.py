"""Parse raw results from the TJES jurisprudence search."""
import pandas as pd

from juscraper.core.parse_utils import coerce_date_columns

# Source field name in the Solr response -> canonical output column name.
_FIELD_RENAMES = {
    "nr_processo": "processo",
    "magistrado": "relator",
    "classe_judicial": "classe",
    "assunto_principal": "assunto",
}

_MAIN_FIELDS = [
    "processo",
    "ementa",
    "relator",
    "orgao_julgador",
    "classe",
    "classe_judicial_sigla",
    "assunto",
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


def _normalizar_documento(documento: dict, campos: list[str]) -> dict:
    """Seleciona campos e junta listas na ordem recebida, mantendo escalares."""
    linha = {}
    for campo in campos:
        valor = documento.get(campo)
        if isinstance(valor, list):
            valor = "; ".join(str(item) for item in valor) if valor else None
        linha[_FIELD_RENAMES.get(campo, campo)] = valor
    return linha


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
    campos_origem = list(_FIELD_RENAMES) + [
        campo for campo in _MAIN_FIELDS + _EXTRA_FIELDS if campo not in _FIELD_RENAMES.values()
    ]
    linhas: list[dict] = []
    for pagina in resultados_brutos:
        documentos = pagina.get("docs", [])
        linhas.extend(_normalizar_documento(documento, campos_origem) for documento in documentos)

    if not linhas:
        return pd.DataFrame()

    df = pd.DataFrame(linhas)

    coerce_date_columns(df, ["dt_juntada"])

    # Reorder: main fields first
    principais = [coluna for coluna in _MAIN_FIELDS if coluna in df.columns]
    extras = [coluna for coluna in df.columns if coluna not in _MAIN_FIELDS]
    df = df[principais + extras]

    return df
