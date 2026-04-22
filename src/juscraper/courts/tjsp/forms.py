"""Form body builder for TJSP cjsg.

Constrói o payload que o TJSP de fato aceita em
``https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do``. Diverge do builder
eSAJ-puro (`juscraper.courts._esaj.forms.build_cjsg_form_body`) em três
pontos funcionais:

- Não envia ``conversationId`` (TJSP não propaga esse campo no POST
  inicial; o ID é extraído da resposta e colado só nas requests de
  paginação subsequentes via ``CJSG_EXTRACT_CONVERSATION_ID``).
- Não envia ``dados.dtPublicacaoInicio/Fim`` (o form do TJSP não tem o
  par de campos de publicação; só filtra por julgamento).
- Mapeia ``baixar_sg: bool`` em ``dados.origensSelecionadas``
  (``"T"`` quando ``True``, ``"R"`` quando ``False``) em vez de aceitar
  ``origem: Literal["T","R"]`` direto — a API pública do TJSP sempre
  expôs o toggle booleano.

O helper de teste ``tests/fixtures/capture/_util.py::make_tjsp_cjsg_body``
espelha a saída desta função para permitir que os contratos offline
verifiquem o payload via ``urlencoded_params_matcher``.
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
