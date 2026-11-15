"""
Functions for parsing DATAJUD API responses
"""
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def contagem_da_resposta(api_response: object) -> tuple[int, str]:
    """``count`` e ``relation`` de ``hits.total`` na resposta de ``contar_processos``.

    A página 1 de ``listar_processos`` passa pela mesma regra.

    Raises:
        TypeError: JSON na forma errada: resposta que não é objeto, sem o
            objeto ``hits.total``, com ``value`` que não é inteiro ou
            ``relation`` fora de ``"eq"``/``"gte"``. A contagem a converte em
            linha ``json_invalido``, em vez de levantar ou inventar ``count=0``.
    """
    if not isinstance(api_response, dict):
        raise TypeError("Resposta DataJud deve ser um objeto JSON.")
    hits = api_response.get("hits")
    total = hits.get("total") if isinstance(hits, dict) else None
    if not isinstance(total, dict):
        raise TypeError("Campo 'hits.total' da resposta DataJud deve ser um objeto.")
    value, relation = total.get("value"), total.get("relation", "eq")
    # ``bool`` herda de ``int``: ``True`` não é contagem.
    if not isinstance(value, int) or isinstance(value, bool) or relation not in ("eq", "gte"):
        raise TypeError(f"Campo 'hits.total' da resposta DataJud fora do formato: {total!r}.")
    return value, relation


def parse_datajud_api_response(
    api_response_json: dict[str, Any] | None,
    mostrar_movs: bool = True
) -> pd.DataFrame:
    """
    Converte a resposta JSON do DataJud em um DataFrame.

    Respostas malformadas geram exceção de parsing, em vez de serem tratadas
    como buscas sem resultados.

    Args:
        api_response_json (dict[str, Any] | None): Resposta JSON da API,
            obtida por ``call_datajud_api``.
        mostrar_movs (bool): Inclui movimentações no DataFrame quando verdadeiro.

    Returns:
        Processos encontrados. Retorna um DataFrame vazio quando
            a resposta é ``None`` ou ``hits.hits`` é uma lista vazia.

    Raises:
        TypeError: Quando ``hits.hits`` não for uma lista.
        AttributeError: Quando um elemento de ``hits.hits`` não for um objeto.
        ValueError: Quando um hit não contiver ``_source``.
    """
    if api_response_json is None:
        logger.warning("Received None for API response, cannot parse.")
        return pd.DataFrame()

    hits = api_response_json.get("hits", {}).get("hits")
    if not isinstance(hits, list):
        raise TypeError("Campo 'hits.hits' da resposta DataJud deve ser uma lista.")
    if not hits:
        logger.info("No 'hits' found in API response.")
        return pd.DataFrame()

    processos = []
    for hit in hits:
        # _source contains the actual document data
        processo_data = hit.get("_source")
        if processo_data is None:
            raise ValueError(f"Hit sem campo '_source': {hit.get('_id', 'N/A')}")

        # Handle 'movimentacoes' based on mostrar_movs flag
        if not mostrar_movs:
            # Create a new dict excluding movimentacoes to avoid modifying original
            processo_data_filtered = {
                key: value for key, value in processo_data.items()
                if key not in ["movimentacoes", "movimentos"]  # Check for both common keys
            }
            processos.append(processo_data_filtered)
        else:
            processos.append(processo_data)  # Include all fields

    return pd.DataFrame(processos)
