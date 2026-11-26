"""Pydantic schemas shared by the TRF PJe ConsultaPública scrapers.

TRF5 (and TJPE's 1º grau) expose the same ``cpopg`` public signature, so
a single pair of schemas serves all of them, mirroring how the eSAJ family shares
``InputCJSGEsajPuro`` across TJAC/TJAL/TJAM/TJCE/TJMS. The schema-coverage
tables in ``tests/schemas/`` map ``trf5`` and ``tjpe`` (``cpopg``) to
these classes; TRF3 and TRF1 left the family for the JSON API and have their
own schemas in ``juscraper.courts.trf3.schemas`` and
``juscraper.courts.trf1.schemas``.
"""
from __future__ import annotations

from pydantic import ConfigDict

from ...schemas import CnjInputBase, OutputCnjConsultaBase


class InputCpopgTRF(CnjInputBase):
    """Accepted input for ``TRF5Scraper.cpopg`` and ``TJPEScraper.cpopg``.

    Inherits ``id_cnj``; aceita também os filtros opcionais de download
    de peças (``download_pecas`` + ``diretorio``). A obrigatoriedade de
    rodar o download de peças na mesma sessão do detalhe (tokens ``ca``
    amarrados à conversa Seam) é o motivo de viver junto com ``cpopg``
    em vez de num método separado.
    """

    download_pecas: bool = False
    diretorio: str | None = None


class OutputCpopgTRF(OutputCnjConsultaBase):
    """Columns produced by ``TRF5Scraper.cpopg`` and ``TJPEScraper.cpopg``.

    Pivot ``id_cnj`` is inherited from :class:`OutputCnjConsultaBase`. The
    rich detail fields populated by :func:`juscraper.courts._trf.parse.parse_detail`
    (``processo``, ``classe``, ``assunto``, ``data_distribuicao``,
    ``orgao_julgador``, ``jurisdicao``, ``endereco_orgao`` and the list-typed
    ``polo_ativo``, ``polo_passivo``, ``movimentacoes``, ``documentos``) and
    ``motivo_falha`` (``None``, or the failure reason of the row) flow through
    ``extra='allow'``. Com ``download_pecas=True``, entram também ``pecas``
    (caminhos salvos) e ``pecas_falhas`` (``[{"id", "motivo_falha"}]`` das
    peças que faltam).
    """

    model_config = ConfigDict(extra="allow")
