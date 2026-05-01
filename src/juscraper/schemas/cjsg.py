"""Base pydantic schemas for jurisprudence search endpoints."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from .mixins import PaginasMixin


class SearchBase(PaginasMixin):
    """Minimum input accepted by any jurisprudence search (cjsg/cjpg).

    ``paginas`` e herdado de :class:`PaginasMixin` — fonte unica do contrato
    ``int | list[int] | range | None``, compartilhada com agregadores que
    nao tem ``pesquisa`` (ex.: :class:`InputListarProcessosDataJud`).

    **Nao inclui filtros de data** propositalmente — nem todo tribunal
    suporta ``data_julgamento_*`` ou ``data_publicacao_*``. Quem suporta
    compoe os mixins :class:`DataJulgamentoMixin` /
    :class:`DataPublicacaoMixin` em :mod:`juscraper.schemas.mixins`.
    """

    pesquisa: str

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
    data_julgamento: date | str | None = None

    model_config = ConfigDict(extra="allow")
