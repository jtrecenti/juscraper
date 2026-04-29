"""Pydantic schemas for TRF6 endpoints (only ``cpopg`` implemented)."""
from __future__ import annotations

from pydantic import ConfigDict

from ...schemas import CnjInputBase, OutputCnjConsultaBase


class InputCpopgTRF6(CnjInputBase):
    """Accepted input for :meth:`TRF6Scraper.cpopg`. Inherits ``id_cnj`` only."""


class OutputCpopgTRF6(OutputCnjConsultaBase):
    """Columns produced by :meth:`TRF6Scraper.cpopg`.

    Pivot ``id_cnj`` is inherited from :class:`OutputCnjConsultaBase`. The
    rich detail fields populated by :func:`juscraper.courts.trf6.parse.parse_detail`
    (``processo``, ``classe``, ``data_autuacao``, ``situacao``, ``magistrado``,
    ``orgao_julgador``, ``assuntos``, ``polo_ativo``, ``polo_passivo``,
    ``mpf``, ``perito``, ``movimentacoes``) flow through ``extra='allow'``.
    Same convention as :class:`OutputCPOPGJusBR` / :class:`OutputCPOPGTJSP`.
    """

    model_config = ConfigDict(extra="allow")
