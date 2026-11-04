"""
Functions for parsing DATAJUD API responses
"""
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


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
        pd.DataFrame: Processos encontrados. Retorna um DataFrame vazio quando
            a resposta é ``None`` ou ``hits.hits`` é uma lista vazia.

    Raises:
        TypeError: Quando ``hits.hits`` não for uma lista.
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

    if not processos:
        logger.info("No process data extracted from hits.")
        return pd.DataFrame()

    return pd.DataFrame(processos)
