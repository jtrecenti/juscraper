"""Base pydantic schemas for jurisprudence search endpoints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SearchBase(BaseModel):
    """Minimum input accepted by any jurisprudence search (cjsg/cjpg).

    ``paginas`` is typed ``list[int] | range | None`` because the
    scraper normalizes ``int`` to ``range`` via
    :func:`juscraper.utils.params.normalize_paginas` **before** building
    this model. The public method signature still accepts ``int``.
    """

    pesquisa: str
    paginas: list[int] | range | None = None
    data_julgamento_inicio: str | None = None
    data_julgamento_fim: str | None = None

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
