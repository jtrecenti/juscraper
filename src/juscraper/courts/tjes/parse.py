"""Parse raw results from the TJES jurisprudence search."""
import pandas as pd

from juscraper.core.parse_utils import coerce_date_columns, normalizar_colunas_texto

# Source field name in the Solr response -> canonical output column name.
_FIELD_RENAMES = {
    "nr_processo": "processo",
    "magistrado": "relator",
    "classe_judicial": "classe",
    "assunto_principal": "assunto",
}

# Os cores legados guardam os mesmos dados sob outros nomes. Campo de origem ->
# coluna canonica, por core (``core_used`` da resposta).
_CAMPOS_POR_CORE_LEGADO = {
    "legado": {
        "numero_processo_legado": "processo",
        "conteudo_decisao_html": "ementa",
        "nome_desembargador": "relator",
        "orgao_julgador": "orgao_julgador",
        "data_julgamento": "data_julgamento",
        "data_publicacao": "data_publicacao",
        "id": "id",
        "conteudo_decisao_completa_html": "acordao",
    },
    "turma_recursal_legado": {
        "num_processo": "processo",
        "cont_ementa": "ementa",
        "nome_juiz": "relator",
        "orgao_julgador": "orgao_julgador",
        "classe_processo": "classe",
        "data_julgamento": "data_julgamento",
        "id": "id",
    },
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

# Ordem das colunas: as principais primeiro, com as datas dos cores legados.
_ORDEM_COLUNAS = [*_MAIN_FIELDS, "data_julgamento", "data_publicacao"]

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


def _normalizar_documento(documento: dict, campos: dict[str, str]) -> dict:
    """Seleciona campos e junta listas na ordem recebida, mantendo escalares."""
    linha = {}
    for campo, coluna in campos.items():
        valor = documento.get(campo)
        if isinstance(valor, list):
            valor = "; ".join(str(item) for item in valor) if valor else None
        linha[coluna] = valor
    return linha


def cjsg_parse(resultados_brutos: list) -> pd.DataFrame:
    """Extrai os dados estruturados dos resultados brutos da pesquisa do TJES.

    Args:
        resultados_brutos: Lista das respostas JSON brutas de ``cjsg_download``.

    Returns:
        Uma linha por decisão. Nos cores ``legado`` e ``turma_recursal_legado``,
            as colunas canonicas vem dos campos proprios do core (ver
            ``_CAMPOS_POR_CORE_LEGADO``), e a data e ``data_julgamento`` (mais
            ``data_publicacao`` no ``legado``), em vez de ``dt_juntada``.
    """
    campos_padrao = dict(_FIELD_RENAMES) | {
        campo: campo for campo in _MAIN_FIELDS + _EXTRA_FIELDS if campo not in _FIELD_RENAMES.values()
    }
    linhas: list[dict] = []
    for pagina in resultados_brutos:
        campos = _CAMPOS_POR_CORE_LEGADO.get(pagina.get("core_used"), campos_padrao)
        documentos = pagina.get("docs", [])
        linhas.extend(_normalizar_documento(documento, campos) for documento in documentos)

    if not linhas:
        return pd.DataFrame()

    df = pd.DataFrame(linhas)

    coerce_date_columns(df, ["dt_juntada", "data_julgamento", "data_publicacao"])
    normalizar_colunas_texto(df, ["ementa", "acordao"])

    # Reorder: main fields first
    principais = [coluna for coluna in _ORDEM_COLUNAS if coluna in df.columns]
    extras = [coluna for coluna in df.columns if coluna not in _ORDEM_COLUNAS]
    df = df[principais + extras]

    return df
