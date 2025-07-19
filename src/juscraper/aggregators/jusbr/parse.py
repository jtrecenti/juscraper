"""
Module parse.py: Functions for parsing and cleaning results and documents from JUSBR.
Includes utilities for processing API responses and cleaning document texts.
"""

# Functions for parsing and cleaning results and documents from JUSBR

import logging
from typing import Optional, Dict, Any, List, Union

logger = logging.getLogger(__name__)

def parse_process_list_response(json_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parses the JSON response from fetching the process list.
    Returns the list of process items under the 'content' key.
    """
    if json_data is None:
        return []
    processos_content = json_data.get('content', [])
    if not isinstance(processos_content, list):
        logger.warning(
            "Chave 'content' não é uma lista ou está ausente"
            "na resposta da lista de processos: %s", 
            json_data
        )
        return []
    return processos_content

def parse_process_details_response(json_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]],
                                   cnj_searched: str) -> Optional[Dict[str, Any]]:
    """
    Parses the JSON response for process details.
    Adds 'processo_pesquisado' to the data.
    Handles cases where API returns a list with a single details object.
    """
    if json_data is None:
        logger.warning(
            "No JSON data received for process details for CNJ: %s", cnj_searched
        )
        return None

    details_dict: Optional[Dict[str, Any]] = None

    if isinstance(json_data, list):
        if json_data:  # Check if list is not empty
            if isinstance(json_data[0], dict):
                details_dict = json_data[0]
                if len(json_data) > 1:
                    logger.warning(
                        "Process details API returned a list with %d"
                        "items for CNJ %s, using only the first.",
                        len(json_data), cnj_searched
                    )
            else:
                logger.error(
                    "Process details API returned a list, but the first item"
                    "is not a dictionary for CNJ %s. Data: %s",
                    cnj_searched, str(json_data[0])[:200] # Log snippet of problematic data
                )
                return None
        else:
            logger.warning("Process details API returned an empty list for CNJ: %s", cnj_searched)
            return None
    elif isinstance(json_data, dict):
        details_dict = json_data

    # Can add more sophisticated parsing here if needed, e.g., flattening nested structures
    # For now, it mostly returns the JSON data, augmented with the searched CNJ.
    parsed_data = {
        'processo': cnj_searched, # Matches screenshot column 'processo'
        'numeroProcesso': details_dict.get('numeroProcesso'), # Matches screenshot
        'idCodexTribunal': details_dict.get('idCodexTribunal'), # Matches screenshot
        'detalhes': details_dict # Full details dictionary as per screenshot
    }
    return parsed_data

def clean_document_text(text_content: Optional[str]) -> Optional[str]:
    """
    Cleans the raw text content of a document.
    """
    if not text_content:
        return None
    try:
        # Comprehensive cleaning based on original code and common issues
        cleaned_text = text_content.replace('\x00', '')  # Remove null characters
        cleaned_text = cleaned_text.replace('\x1a', '')  # Remove SUB character
        cleaned_text = cleaned_text.replace('\r\n', '\n').replace('\r', '\n') # Normalize newlines
        cleaned_text = cleaned_text.replace('\xa0', ' ')    # non-breaking space to regular space
        cleaned_text = cleaned_text.replace('\u2028', '\n') # Line separator to newline
        cleaned_text = cleaned_text.replace('\u2029', '\n') # Paragraph separator to nl
        cleaned_text = cleaned_text.strip() # Strip leading/trailing whitespace
        # Potentially add more specific cleaning if other problematic characters are found
        return cleaned_text
    except Exception as e:
        # Catching Exception as a last resort to avoid crashing
        # on unexpected text cleaning errors.
        # All known issues should be handled above; this logs
        # and continues for unpredictable encoding/corruption.
        logger.error(
            "Erro ao limpar texto do documento: %s. Conteúdo (início): %s",
            e, str(text_content)[:100]
        )
        return None
