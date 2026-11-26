"""
Functions for parsing specific to TJDFT
"""
from juscraper.core.parse_utils import normalizar_texto

# Chaves da API com nome canonico no projeto (refs #12). As demais passam como
# vem: ``codigoClasseCnj``, por exemplo, e o codigo da classe, nao o nome que
# ``classe`` traz nos outros tribunais.
_RENOMEAR = {
    "nomeRelator": "relator",
    "descricaoOrgaoJulgador": "orgao_julgador",
    "dataJulgamento": "data_julgamento",
    "dataPublicacao": "data_publicacao",
}


def cjsg_parse(resultados_brutos):
    """Uma linha por registro da API, com as chaves de :data:`_RENOMEAR` renomeadas.

    A ``ementa`` passa por :func:`normalizar_texto`.
    """
    return [
        {
            _RENOMEAR.get(chave, chave): normalizar_texto(valor) if chave == "ementa" else valor
            for chave, valor in item.items()
        }
        for item in resultados_brutos
    ]
