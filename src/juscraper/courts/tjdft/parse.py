"""
Functions for parsing specific to TJDFT
"""

def cjsg_parse(resultados_brutos):
    """
    Extracts structured information from the raw TJDFT search results.
    Returns all fields present in each item (list of dictionaries).
    """
    return [dict(item) for item in resultados_brutos]
