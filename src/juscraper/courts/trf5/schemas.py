"""Pydantic schemas for TRF5 endpoints (only ``cpopg`` implemented)."""
from __future__ import annotations

from pydantic import ConfigDict

from ...schemas import CnjInputBase, OutputCnjConsultaBase


class InputCpopgTRF5(CnjInputBase):
    """Accepted input for :meth:`TRF5Scraper.cpopg`. Inherits ``id_cnj`` only."""


class OutputCpopgTRF5(OutputCnjConsultaBase):
    """Columns produced by :meth:`TRF5Scraper.cpopg`.

    Pivot ``id_cnj`` is inherited from :class:`OutputCnjConsultaBase`. The
    rich detail fields populated by :func:`juscraper.courts.trf5.parse.parse_detail`
    (``processo``, ``classe``, ``assunto``, ``data_distribuicao``,
    ``orgao_julgador``, ``jurisdicao``, ``endereco_orgao`` and the list-typed
    ``polo_ativo``, ``polo_passivo``, ``movimentacoes``, ``documentos``) flow
    through ``extra='allow'``. Same convention as :class:`OutputCPOPGJusBR` /
    :class:`OutputCPOPGTJSP`.
    """

    model_config = ConfigDict(extra="allow")
