"""Funcoes de download para o agregador ComunicaCNJ.

A API publica de Comunicacoes Processuais do CNJ
(``https://comunicaapi.pje.jus.br/api/v1/comunicacao``) e um endpoint REST
GET com paginacao 1-based. Cada chamada devolve um JSON com:

- ``count`` (int): total de comunicacoes que casam com o filtro.
- ``items`` (list[dict]): pagina atual.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"

DEFAULT_HEADERS: Dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "pt-BR,en-US;q=0.7,en;q=0.3",
    "Connection": "keep-alive",
    "Origin": "https://comunica.pje.jus.br",
    "Referer": "https://comunica.pje.jus.br/",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) "
        "Gecko/20100101 Firefox/139.0"
    ),
}


def build_listar_comunicacoes_params(
    *,
    pesquisa: str,
    pagina: int,
    itens_por_pagina: int = 100,
    data_disponibilizacao_inicio: Optional[str] = None,
    data_disponibilizacao_fim: Optional[str] = None,
) -> Dict[str, Any]:
    """Monta a querystring aceita pelo endpoint de listagem.

    Args:
        pesquisa: Termo de busca (parametro ``texto``).
        pagina: Numero da pagina (1-based).
        itens_por_pagina: Resultados por pagina (1-100).
        data_disponibilizacao_inicio: ISO ``YYYY-MM-DD`` para o param
            ``dataDisponibilizacaoInicio`` da API.
        data_disponibilizacao_fim: ISO ``YYYY-MM-DD`` para o param
            ``dataDisponibilizacaoFim`` da API.
    """
    params: Dict[str, Any] = {
        "itensPorPagina": itens_por_pagina,
        "pagina": pagina,
        "texto": pesquisa,
    }
    if data_disponibilizacao_inicio is not None:
        params["dataDisponibilizacaoInicio"] = data_disponibilizacao_inicio
    if data_disponibilizacao_fim is not None:
        params["dataDisponibilizacaoFim"] = data_disponibilizacao_fim
    return params


def call_comunica_api(
    session: requests.Session,
    params: Dict[str, Any],
    *,
    timeout: float = 30.0,
) -> requests.Response:
    """Faz uma requisicao GET ao endpoint e devolve a Response.

    O caller decide como tratar o body (parse JSON, raise_for_status, etc).
    """
    response = session.get(BASE_URL, params=params, timeout=timeout)
    return response
