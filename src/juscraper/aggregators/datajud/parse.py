"""
Functions for parsing DATAJUD API responses
"""
import pandas as pd
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def parse_datajud_api_response(
    api_response_json: Optional[Dict[str, Any]], 
    mostrar_movs: bool = True
) -> pd.DataFrame:
    """
    Parses the JSON response from the Datajud API into a pandas DataFrame.

    Args:
        api_response_json (Optional[Dict[str, Any]]): The parsed JSON response from the API 
                                                       (output of call_datajud_api).
        mostrar_movs (bool): If True, includes 'movimentacoes' in the DataFrame. 
                             Otherwise, they are excluded.

    Returns:
        pd.DataFrame: A DataFrame containing the process data. Returns an empty 
                      DataFrame if parsing fails or no data is found.
    """
    if api_response_json is None:
        logger.warning("Received None for API response, cannot parse.")
        return pd.DataFrame()

    try:
        hits = api_response_json.get("hits", {}).get("hits", [])
        if not hits:
            logger.info("No 'hits' found in API response.")
            return pd.DataFrame()

        processos = []
        for hit in hits:
            # _source contains the actual document data
            processo_data = hit.get("_source")
            if processo_data is None:
                logger.warning(f"Hit found without '_source' field: {hit.get('_id', 'N/A')}")
                continue

            # Handle 'movimentacoes' based on mostrar_movs flag
            if not mostrar_movs:
                # Create a new dict excluding movimentacoes to avoid modifying original
                processo_data_filtered = {
                    key: value for key, value in processo_data.items()
                    if key not in ["movimentacoes", "movimentos"] # Check for both common keys
                }
                processos.append(processo_data_filtered)
            else:
                processos.append(processo_data) # Include all fields

        if not processos:
            logger.info("No process data extracted from hits.")
            return pd.DataFrame()

        df = pd.DataFrame(processos)
        return df

    except Exception as e:
        logger.error("Error parsing Datajud API JSON response: %s", e)
        logger.debug("Problematic JSON (or part of it): %s", str(api_response_json)[:500])
        return pd.DataFrame()
