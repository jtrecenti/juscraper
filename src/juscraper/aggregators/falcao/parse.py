"""Parsing das respostas do endpoint Falcao ``/no-auth/pesquisa``.

Cada colecao (:data:`.schemas.COLECOES`) devolve um shape proprio, mas todas
compartilham o mesmo envelope ``{documentos, quantidadeTotal, temasTopFive}``.
:func:`parse_documentos` normaliza um nucleo canonico comum (``processo``,
``colecao``, ``relator``, ``classe``, ``data_julgamento``, ``data_juntada``) e
propaga os demais campos brutos da colecao inalterados.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Chaves brutas candidatas a virar a coluna canonica ``classe`` — ordem de
# preferencia (a primeira presente vence). Colecoes distintas usam nomes
# diferentes para o mesmo conceito.
_CLASSE_KEYS: tuple[str, ...] = (
    "classeProcesso",
    "classeProcessualPorExtenso",
    "classeProcessual",
)


def parse_total(data: dict[str, Any]) -> int:
    """Le ``quantidadeTotal`` do envelope JSON.

    Levanta ``ValueError`` quando a chave nao existe — sinal de que a API
    mudou de shape e o parser precisa acompanhar.
    """
    total = data.get("quantidadeTotal")
    if total is None:
        raise ValueError(
            "Resposta JSON do Falcao nao contem 'quantidadeTotal'."
        )
    return int(total)


def _normalizar_documento(raw: dict[str, Any], colecao: str) -> dict[str, Any]:
    """Aplica os renames canonicos a um documento bruto, preservando o resto."""
    doc = dict(raw)

    # processo: numeroProcesso na maioria; a colecao 'precedentes' usa 'numero'.
    processo = doc.pop("numeroProcesso", None)
    if processo is None:
        processo = doc.get("numero")
    doc["processo"] = processo

    doc["colecao"] = colecao

    # relator: 'acordaos' ja traz 'relator'; as demais usam 'nomeRelator'.
    if "relator" not in doc and doc.get("nomeRelator") is not None:
        doc["relator"] = doc["nomeRelator"]

    # datas -> snake_case canonico.
    if "dataJulgamento" in doc:
        doc["data_julgamento"] = doc.pop("dataJulgamento")
    if "dataJuntada" in doc:
        doc["data_juntada"] = doc.pop("dataJuntada")

    # classe: primeira chave bruta disponivel.
    if "classe" not in doc:
        for chave in _CLASSE_KEYS:
            if doc.get(chave):
                doc["classe"] = doc[chave]
                break

    return doc


def parse_documentos(data: dict[str, Any], colecao: str) -> list[dict[str, Any]]:
    """Extrai e normaliza a lista ``documentos`` do envelope JSON.

    Args:
        data: JSON ja decodificado da resposta.
        colecao: Colecao consultada (usada para preencher a coluna ``colecao``
            e escolher os renames apropriados).

    Returns:
        Lista de dicionarios prontos para virar linhas de ``pd.DataFrame``,
        cada um com as colunas canonicas garantidas (:class:`.schemas.
        OutputCJSGFalcao`) alem dos campos brutos da colecao.
    """
    documentos = data.get("documentos")
    if documentos is None:
        return []
    return [_normalizar_documento(doc, colecao) for doc in documentos]
