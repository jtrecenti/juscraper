"""Form body builders for eSAJ cjsg POST.

Mirrors the exact payload sent by the 5 eSAJ-puros scrapers
(TJAC/TJAL/TJAM/TJCE/TJMS) before this refactor. TJSP has a slightly
different body (no ``conversationId``, no ``dtPublicacao*``, different
field order) and builds its own in ``juscraper.courts.tjsp.forms``.
"""
from __future__ import annotations

from typing import Any


def build_cjsg_form_body(
    *,
    pesquisa: str,
    ementa: str | None = None,
    numero_recurso: str | None = None,
    classe: str | None = None,
    assunto: str | None = None,
    comarca: str | None = None,
    orgao_julgador: str | None = None,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    origem: str = "T",
    tipo_decisao: str = "acordao",
) -> dict[str, Any]:
    """Return the form body expected by ``cjsg/resultadoCompleta.do`` (eSAJ-puros)."""
    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    return {
        "conversationId": "",
        "dados.buscaInteiroTeor": pesquisa,
        "dados.pesquisarComSinonimos": "S",
        "dados.buscaEmenta": ementa or "",
        "dados.nuProcOrigem": numero_recurso or "",
        "dados.nuRegistro": "",
        "agenteSelectedEntitiesList": "",
        "contadoragente": "0",
        "contadorMaioragente": "0",
        "codigoCr": "",
        "codigoTr": "",
        "nmAgente": "",
        "juizProlatorSelectedEntitiesList": "",
        "contadorjuizProlator": "0",
        "contadorMaiorjuizProlator": "0",
        "codigoJuizCr": "",
        "codigoJuizTr": "",
        "nmJuiz": "",
        "classesTreeSelection.values": classe or "",
        "classesTreeSelection.text": "",
        "assuntosTreeSelection.values": assunto or "",
        "assuntosTreeSelection.text": "",
        "comarcaSelectedEntitiesList": "",
        "contadorcomarca": "1",
        "contadorMaiorcomarca": "1",
        "cdComarca": comarca or "",
        "nmComarca": "",
        "secoesTreeSelection.values": orgao_julgador or "",
        "secoesTreeSelection.text": "",
        "dados.dtJulgamentoInicio": data_julgamento_inicio or "",
        "dados.dtJulgamentoFim": data_julgamento_fim or "",
        "dados.dtRegistroInicio": "",
        "dados.dtRegistroFim": "",
        "dados.dtPublicacaoInicio": data_publicacao_inicio or "",
        "dados.dtPublicacaoFim": data_publicacao_fim or "",
        "dados.origensSelecionadas": origem,
        "tipoDecisaoSelecionados": tipo_param,
        "dados.ordenacao": "dtPublicacao",
    }
