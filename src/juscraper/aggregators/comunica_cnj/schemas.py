"""Pydantic schemas for the ComunicaCNJ aggregator.

A API publica em https://comunicaapi.pje.jus.br/api/v1/comunicacao aceita
filtros opcionais por intervalo de data de disponibilizacao em formato ISO
(``YYYY-MM-DD``). Datas em formato brasileiro (``DD/MM/YYYY``) sao convertidas
no client antes de instanciar o schema.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ...schemas import PaginasMixin


class InputListarComunicacoesComunicaCNJ(PaginasMixin):
    """Filtros aceitos por :meth:`ComunicaCNJScraper.listar_comunicacoes`.

    Campos:
        pesquisa: Termo livre buscado no texto da comunicacao (parametro
            ``texto`` da API). Obrigatorio.
        data_disponibilizacao_inicio: Limite inferior de
            ``dataDisponibilizacao``, ISO ``YYYY-MM-DD``. Opcional.
        data_disponibilizacao_fim: Limite superior de
            ``dataDisponibilizacao``, ISO ``YYYY-MM-DD``. Opcional.
        itens_por_pagina: Quantos resultados por requisicao (1-100). Default
            100 para minimizar round-trips.

    Os nomes ``data_inicio``/``data_fim`` ficaram **fora** do canonico de
    proposito: no resto do juscraper, esses dois sao aliases deprecados que
    ``normalize_datas`` mapeia para ``data_julgamento_inicio``/
    ``data_julgamento_fim``. O ComunicaCNJ filtra por data de
    disponibilizacao (semantica diferente), entao usar nome explicito evita
    colisao com o pipeline canonico (``DEPRECATED_ALIASES``/``DATE_ALIASES``
    em ``utils/params.py``).
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    pesquisa: str
    data_disponibilizacao_inicio: str | None = None
    data_disponibilizacao_fim: str | None = None
    itens_por_pagina: int = Field(default=100, ge=1, le=100)

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class OutputListarComunicacoesComunicaCNJ(BaseModel):
    """Colunas observaveis em uma linha do DataFrame de
    :meth:`ComunicaCNJScraper.listar_comunicacoes`.

    A API devolve cada item com ``numero_processo`` (CNJ formatado) +
    diversos campos camelCase relativos ao tribunal de origem (``siglaTribunal``,
    ``nomeOrgao``, ``texto``, ``link``, ``dataDisponibilizacao``, etc.).
    A coluna minima garantida e ``numero_processo``; ``extra='allow'``
    propaga o restante do passthrough sem precisar enumerar campo a campo.
    """

    numero_processo: str

    model_config = ConfigDict(extra="allow")
