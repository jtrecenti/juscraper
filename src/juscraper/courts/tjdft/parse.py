"""
Functions for parsing specific to TJDFT
"""
from juscraper.core.parse_utils import normalizar_texto


def cjsg_parse(resultados_brutos):
    """
    Extracts structured information from the raw TJDFT search results.
    Returns all fields present in each item (list of dictionaries), with the
    ``ementa`` passed through :func:`normalizar_texto`.
    """
    registros = [dict(item) for item in resultados_brutos]
    for registro in registros:
        if "ementa" in registro:
            registro["ementa"] = normalizar_texto(registro["ementa"])
    return registros
