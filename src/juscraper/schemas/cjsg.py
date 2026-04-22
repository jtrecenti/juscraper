"""Base pydantic schemas for jurisprudence search endpoints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SearchBase(BaseModel):
    """Minimum input accepted by any jurisprudence search (cjsg/cjpg).

    ``paginas`` aceita ``int`` / ``list[int]`` / ``range`` / ``None``. Em
    scrapers ja refatorados (wired), :func:`juscraper.utils.params.normalize_paginas`
    converte ``int`` em ``range`` *antes* do pydantic — mas o schema aceita
    ``int`` para refletir a API publica.

    **Nao inclui filtros de data** propositalmente — nem todo tribunal
    suporta ``data_julgamento_*`` ou ``data_publicacao_*``. Quem suporta
    compoe os mixins :class:`DataJulgamentoMixin` /
    :class:`DataPublicacaoMixin` em :mod:`juscraper.schemas.mixins`.
    """

    pesquisa: str
    paginas: int | list[int] | range | None = None

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class OutputCJSGBase(BaseModel):
    """Minimum output columns guaranteed by any cjsg DataFrame row."""

    processo: str
    ementa: str
    data_julgamento: str | None = None

    model_config = ConfigDict(extra="allow")
