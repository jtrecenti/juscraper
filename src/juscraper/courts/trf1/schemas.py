"""Pydantic schemas for TRF1 endpoints (only ``cpopg`` implemented)."""
from __future__ import annotations

from pydantic import ConfigDict

from ...schemas import CnjInputBase, OutputCnjConsultaBase


class InputCpopgTRF1(CnjInputBase):
    """Accepted input for :meth:`TRF1Scraper.cpopg`. Inherits ``id_cnj`` only."""


class OutputCpopgTRF1(OutputCnjConsultaBase):
    """Columns produced by :meth:`TRF1Scraper.cpopg`.

    Pivot ``id_cnj`` is inherited from :class:`OutputCnjConsultaBase`. The
    rich detail fields populated by :func:`juscraper.courts.trf1.parse.parse_detail`
    (``processo``, ``classe``, ``assunto``, ``data_distribuicao``,
    ``orgao_julgador``, ``jurisdicao``, ``endereco_orgao`` and the list-typed
    ``polo_ativo``, ``polo_passivo``, ``movimentacoes``, ``documentos``) flow
    through ``extra='allow'``. Same convention as :class:`OutputCpopgTRF3` /
    :class:`OutputCpopgTRF5`.
    """

    model_config = ConfigDict(extra="allow")
