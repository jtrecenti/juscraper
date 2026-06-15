"""Pydantic schemas for TRF5 endpoints (only ``cpopg`` implemented)."""
from __future__ import annotations

from pydantic import ConfigDict

from ...schemas import CnjInputBase, OutputCnjConsultaBase


class InputCpopgTRF5(CnjInputBase):
    """Accepted input for :meth:`TRF5Scraper.cpopg`.

    Inherits ``id_cnj``; aceita também os filtros opcionais de download
    de peças (``download_pecas`` + ``diretorio``). A obrigatoriedade de
    rodar o download de peças na mesma sessão do detalhe (tokens ``ca``
    amarrados à conversa Seam) é o motivo de viver junto com ``cpopg``
    em vez de num método separado.
    """

    download_pecas: bool = False
    diretorio: str | None = None


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
