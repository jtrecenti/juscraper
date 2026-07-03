"""Pydantic schemas shared by the TRF PJe ConsultaPública scrapers.

TRF1/TRF3/TRF5 expose the same ``cpopg`` public signature, so a single pair
of schemas serves all three — mirroring how the eSAJ family shares
``InputCJSGEsajPuro`` across TJAC/TJAL/TJAM/TJCE/TJMS. The schema-coverage
tables in ``tests/schemas/`` map ``trf{1,3,5}`` to these classes.
"""
from __future__ import annotations

from pydantic import ConfigDict

from ...schemas import CnjInputBase, OutputCnjConsultaBase


class InputCpopgTRF(CnjInputBase):
    """Accepted input for ``TRF{1,3,5}Scraper.cpopg``.

    Inherits ``id_cnj``; aceita também os filtros opcionais de download
    de peças (``download_pecas`` + ``diretorio``). A obrigatoriedade de
    rodar o download de peças na mesma sessão do detalhe (tokens ``ca``
    amarrados à conversa Seam) é o motivo de viver junto com ``cpopg``
    em vez de num método separado.
    """

    download_pecas: bool = False
    diretorio: str | None = None


class OutputCpopgTRF(OutputCnjConsultaBase):
    """Columns produced by ``TRF{1,3,5}Scraper.cpopg``.

    Pivot ``id_cnj`` is inherited from :class:`OutputCnjConsultaBase`. The
    rich detail fields populated by :func:`juscraper.courts._trf.parse.parse_detail`
    (``processo``, ``classe``, ``assunto``, ``data_distribuicao``,
    ``orgao_julgador``, ``jurisdicao``, ``endereco_orgao`` and the list-typed
    ``polo_ativo``, ``polo_passivo``, ``movimentacoes``, ``documentos``) flow
    through ``extra='allow'``.
    """

    model_config = ConfigDict(extra="allow")
