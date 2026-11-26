"""
Functions for parsing specific to TJDFT
"""

# Chaves da API renomeadas para os nomes canonicos do projeto (refs #12). As
# demais (``decisao``, ``identificador``, ``uuid``, ``codigoClasseCnj``,
# ``turmaRecursal``, ``marcadores``...) passam como vem da API: nao tem
# equivalente canonico. ``codigoClasseCnj`` e o codigo numerico da classe, e
# nao o nome que os demais tribunais entregam em ``classe``.
_RENOMEAR = {
    "nomeRelator": "relator",
    "descricaoOrgaoJulgador": "orgao_julgador",
    "dataJulgamento": "data_julgamento",
    "dataPublicacao": "data_publicacao",
}


def cjsg_parse(resultados_brutos):
    """Uma linha por registro da API, com as chaves de :data:`_RENOMEAR` renomeadas.

    ``nomeRelator``, ``descricaoOrgaoJulgador``, ``dataJulgamento`` e
    ``dataPublicacao`` saem como ``relator``, ``orgao_julgador``,
    ``data_julgamento`` e ``data_publicacao``; as demais chaves do registro
    passam com o nome da API.
    """
    return [{_RENOMEAR.get(chave, chave): valor for chave, valor in item.items()} for item in resultados_brutos]
