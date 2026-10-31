"""
Funções de análise dos resultados de pesquisa de jurisprudência do TJMT.
"""
import re
from datetime import date
from typing import cast

import pandas as pd

CJSG_COLUMNS = (
    "id",
    "tipo",
    "ementa",
    "observacao",
    "processo",
    "classe",
    "assunto",
    "tipo_acao",
    "tipo_processo",
    "relator",
    "redator_designado",
    "orgao_julgador",
    "sigla_classe_feito",
    "data_julgamento",
    "data_publicacao",
    "instancia",
    "origem",
    "julgamento",
)


def _strip_html(text: str) -> str:
    """Remove tags HTML de uma string."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _coerce_tjmt_date(value: object) -> date | None:
    """Converte um timestamp do TJMT para data sem normalizar para UTC."""
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return cast("date", parsed.date())


def _extrair_resultados(page_data: dict) -> list[dict]:
    if page_data.get("success") is not True:
        raise ValueError("Resposta do TJMT indica falha na pesquisa.")
    if page_data.get("errorMessage") is not None:
        raise ValueError("Resposta do TJMT contém uma mensagem de erro.")
    value = page_data.get("value")
    if not isinstance(value, dict):
        raise TypeError("Resposta do TJMT não contém value como objeto JSON.")
    if not isinstance(value.get("resultados"), list):
        raise TypeError("Resposta do TJMT não contém value.resultados como lista.")
    return cast("list[dict]", value["resultados"])


def _mapear_resultado(item: dict) -> dict:
    return {
        "id": item.get("idDocumento"),
        "tipo": item.get("tipo"),
        "ementa": _strip_html(item.get("conteudo", "")),
        "observacao": item.get("observacao"),
        "processo": item.get("numeroUnicoFormatado"),
        "classe": item.get("nomeClasse"),
        "assunto": item.get("assunto"),
        "tipo_acao": item.get("tipoAcao"),
        "tipo_processo": item.get("tipoProcesso"),
        "relator": item.get("nomeRelator"),
        "redator_designado": item.get("nomeRedatorDesignado"),
        "orgao_julgador": item.get("nomeCamara"),
        "sigla_classe_feito": item.get("nomeClasseEsferaProcessual"),
        "data_julgamento": item.get("dataJulgamento"),
        "data_publicacao": item.get("dataPublicacao"),
        "instancia": item.get("instancia"),
        "origem": item.get("origem"),
        "julgamento": item.get("descricaoJulgamento"),
    }


def cjsg_parse(resultados_brutos: list, tipo_consulta: str = "Acordao") -> list[dict]:
    """Extrai registros estruturados das respostas brutas da API do TJMT.

    Argumentos:
        resultados_brutos: Lista de dicionários JSON brutos, um por página.
        tipo_consulta: ``"Acordao"`` ou ``"DecisaoMonocratica"``.

    Retorno:
        Lista de dicionários planos prontos para ``pd.DataFrame``.
    """
    _ = tipo_consulta
    registros = []
    for page_data in resultados_brutos:
        if not isinstance(page_data, dict):
            raise TypeError("Resposta do TJMT deve ser um objeto JSON.")
        for item in _extrair_resultados(page_data):
            if not isinstance(item, dict):
                raise TypeError("Resultado do TJMT deve ser um objeto JSON.")
            registros.append(_mapear_resultado(item))
    return registros


def coerce_tjmt_date_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Converte datas do TJMT individualmente, preservando o dia civil."""
    for column in ("data_julgamento", "data_publicacao"):
        if column in dataframe.columns:
            dataframe[column] = dataframe[column].map(_coerce_tjmt_date)
    return dataframe
