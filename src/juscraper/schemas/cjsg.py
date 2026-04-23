"""Base pydantic schemas for jurisprudence search endpoints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SearchBase(BaseModel):
    """Minimum input accepted by any jurisprudence search (cjsg/cjpg).

    ``paginas`` e **1-based em todos os raspadores** — ``paginas=3`` equivale
    a ``range(1, 4)`` e baixa as paginas 1, 2 e 3. ``paginas=0`` e invalido.
    ``None`` (default) significa "todas as paginas disponiveis" — o scraper
    consulta o backend para descobrir o total. Runtime normaliza
    ``int`` -> ``range`` em :func:`juscraper.utils.params.normalize_paginas`
    antes do pydantic, mas o schema aceita as 4 formas para refletir a API
    publica.

    Este e o **contrato unico** do parametro ``paginas``: schemas concretos
    nao devem redeclarar. Qualquer divergencia por tribunal (ex.: DataJud
    aceitar apenas ``range``) vira bug a ser corrigido, nao particularidade
    a ser documentada.

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
    """Minimum output columns shared by every cjsg DataFrame row.

    ``ementa`` e Optional porque TJGO nao entrega resumo — o parser devolve
    o texto integral do ato em ``texto``. Os demais tribunais preenchem
    ``ementa`` normalmente; a optionality evita ``type: ignore`` em TJGO.
    """

    processo: str
    ementa: str | None = None
    data_julgamento: str | None = None

    model_config = ConfigDict(extra="allow")
