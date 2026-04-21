"""Form body builder for TJSP cjsg.

Mirrors the exact body sent by the original ``tjsp/cjsg_download.py``
byte-for-byte so offline contract matchers (``make_tjsp_cjsg_body``)
continue to accept the request.
"""
from __future__ import annotations

from typing import Any


def build_tjsp_cjsg_body(
    *,
    pesquisa: str,
    ementa: str | None = None,
    classe: str | None = None,
    assunto: str | None = None,
    comarca: str | None = None,
    orgao_julgador: str | None = None,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    baixar_sg: bool = True,
    tipo_decisao: str = "acordao",
) -> dict[str, Any]:
    """Build the POST body for TJSP ``cjsg/resultadoCompleta.do``."""
    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    origem = "T" if baixar_sg else "R"
    return {
        "dados.buscaInteiroTeor": pesquisa,
        "dados.pesquisarComSinonimos": "S",
        "dados.buscaEmenta": ementa or "",
        "dados.nuProcOrigem": "",
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
        "dados.ordenacao": "dtPublicacao",
        "dados.origensSelecionadas": origem,
        "tipoDecisaoSelecionados": tipo_param,
    }
