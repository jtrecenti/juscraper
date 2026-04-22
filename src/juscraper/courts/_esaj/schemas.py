"""Pydantic schemas for eSAJ cjsg (TJAC/TJAL/TJAM/TJCE/TJMS).

TJSP has a divergent public API (``baixar_sg`` vs ``origem``, missing
``numero_recurso``/``data_publicacao_*``) and gets its own schema in
``juscraper.courts.tjsp.schemas``.
"""
from __future__ import annotations

from typing import Literal

from ...schemas.cjsg import OutputCJSGBase, SearchBase


class InputCJSGEsajPuro(SearchBase):
    """Accepted input for TJAC/TJAL/TJAM/TJCE/TJMS ``cjsg``.

    Inherits ``extra='forbid'`` from :class:`SearchBase`, so unknown keyword
    arguments raise ``ValidationError`` instead of being silently ignored.
    """

    ementa: str | None = None
    numero_recurso: str | None = None
    classe: str | None = None
    assunto: str | None = None
    comarca: str | None = None
    orgao_julgador: str | None = None
    data_publicacao_inicio: str | None = None
    data_publicacao_fim: str | None = None
    origem: Literal["T", "R"] = "T"
    tipo_decisao: Literal["acordao", "monocratica"] = "acordao"


class OutputCJSGEsaj(OutputCJSGBase):
    """Columns observable in eSAJ cjsg DataFrames.

    Minimum: ``processo``, ``ementa`` (inherited from :class:`OutputCJSGBase`).
    Added here: canonical eSAJ columns. ``extra='allow'`` is inherited so
    tribunal-specific extras (e.g., ``classe_assunto``) don't break
    validation.
    """

    cd_acordao: str | None = None
    cd_foro: str | None = None
    relator: str | None = None
    orgao_julgador: str | None = None
