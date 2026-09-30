"""Parse das respostas da API do JusBR.

A forma de cada resposta já foi conferida em :mod:`.download`: os ``fetch_*``
levantam ``InvalidJSONResponseError`` para o corpo que não tem a forma do
endpoint, e por isso as funções daqui só leem.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_process_list_response(json_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Devolve os processos da chave ``content`` da listagem.

    ``fetch_process_list`` garante que ``content`` é uma lista de objetos,
    inclusive no 404, que chega como ``{"content": []}``.
    """
    processos: list[dict[str, Any]] = json_data["content"]
    return processos


def parse_process_details_response(
    json_data: dict[str, Any] | list[dict[str, Any]],
    cnj_searched: str,
) -> dict[str, Any]:
    """Monta a linha de :meth:`JusbrScraper.cpopg` a partir dos detalhes do processo.

    A API devolve uma lista com o objeto de detalhes; um objeto solto também
    é aceito. ``fetch_process_details`` garante a lista não vazia com um
    objeto no primeiro item. Quando a lista traz mais de um item, só o
    primeiro é usado, com aviso.
    """
    if isinstance(json_data, dict):
        detalhes = json_data
    else:
        detalhes = json_data[0]
        if len(json_data) > 1:
            logger.warning(
                "A API de detalhes devolveu uma lista com %d itens para o CNJ %s; só o primeiro é usado.",
                len(json_data), cnj_searched,
            )
    return {
        'processo': cnj_searched,
        'numeroProcesso': detalhes.get('numeroProcesso'),
        'idCodexTribunal': detalhes.get('idCodexTribunal'),
        'detalhes': detalhes,
    }
