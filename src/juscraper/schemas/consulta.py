"""Bases compartilhadas para endpoints de consulta processual (cpopg/cposg).

Extraidas por evidencia: aparecem em TJSP (``cpopg``, ``cposg``), JusBR
(``cpopg``) e servem como alicerce para quando os scrapers com stubs
``NotImplementedError`` forem implementados.

``id_cnj`` aceita ``str`` (um numero CNJ) ou ``list[str]`` (varios); os
scrapers iteram quando recebem lista.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CnjInputBase(BaseModel):
    """Input minimo de endpoints de consulta por numero CNJ (``cpopg``/``cposg``)."""

    id_cnj: str | list[str]

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class OutputCnjConsultaBase(BaseModel):
    """Colunas minimas do DataFrame de uma consulta CNJ.

    ``id_cnj`` identifica qual processo gerou a linha — essencial quando o
    metodo recebe varios CNJs.
    """

    id_cnj: str

    model_config = ConfigDict(extra="allow")
