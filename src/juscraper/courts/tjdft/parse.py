"""
Funções de parse específicas para TJDFT
"""

def cjsg_parse(resultados_brutos):
    """
    Extrai informações estruturadas dos resultados brutos do TJDFT.
    Retorna todos os campos presentes em cada item (lista de dicionários).
    """
    return [dict(item) for item in resultados_brutos]
