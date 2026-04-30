"""Pydantic schemas for the ComunicaCNJ aggregator.

A API publica em https://comunicaapi.pje.jus.br/api/v1/comunicacao aceita
filtros opcionais por intervalo de data de disponibilizacao em formato ISO
(``YYYY-MM-DD``). Datas em formato brasileiro (``DD/MM/YYYY``) sao convertidas
no client antes de instanciar o schema.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field

from ...schemas import PaginasMixin


class InputListarComunicacoesComunicaCNJ(PaginasMixin):
    """Filtros aceitos por :meth:`ComunicaCNJScraper.listar_comunicacoes`.

    Campos:
        pesquisa: Termo livre buscado no texto da comunicacao (parametro
            ``texto`` da API). Obrigatorio.
        data_inicio: Limite inferior de ``dataDisponibilizacao``, ISO
            ``YYYY-MM-DD``. Opcional.
        data_fim: Limite superior de ``dataDisponibilizacao``, ISO
            ``YYYY-MM-DD``. Opcional.
        itens_por_pagina: Quantos resultados por requisicao (1-100). Default
            100 para minimizar round-trips.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    pesquisa: str
    data_inicio: str | None = None
    data_fim: str | None = None
    itens_por_pagina: int = Field(default=100, ge=1, le=100)

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )
