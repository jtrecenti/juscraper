"""Parsing de respostas do endpoint ComunicaCNJ.

A API atual devolve ``items`` (em ingles) — versoes anteriores usavam
``itens`` (em portugues). Este parser aceita ambos para compatibilidade,
priorizando ``items``.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


def parse_count(response: requests.Response) -> int:
    """Le o total de resultados a partir da resposta JSON.

    A API expoe o total como ``count``. Levanta ``ValueError`` quando a
    chave nao esta presente — sinal de que a API mudou e o parser precisa
    acompanhar (cf. transicao ``itens`` -> ``items`` ja tratada em
    :func:`parse_items`).
    """
    data = response.json()
    contagem = data.get("count")
    if contagem is None:
        raise ValueError(
            "Resposta JSON do ComunicaCNJ nao contem 'count'."
        )
    return int(contagem)


def parse_items(response: requests.Response) -> list[dict[str, Any]]:
    """Extrai a lista de comunicacoes da resposta.

    A chave canonica e ``items`` (a API mudou de ``itens`` para ``items``
    em algum momento de 2025-2026). Mantemos fallback para ``itens`` por
    seguranca.
    """
    data = response.json()
    items = data.get("items")
    if items is None:
        items = data.get("itens", [])
    return list(items)
