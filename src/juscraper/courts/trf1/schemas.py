"""Schemas pydantic do ``cpopg`` do TRF1 (consulta pública do PJe, API JSON)."""
from __future__ import annotations

from ...schemas import CnjInputBase, OutputCnjConsultaBase
from .._pje_api.schemas import CamposProcessoPJe, DownloadPecasMixin


class InputCpopgTRF1(CnjInputBase, DownloadPecasMixin):
    """Entrada aceita por :meth:`TRF1Scraper.cpopg`.

    Herda ``id_cnj``; ``download_pecas`` + ``diretorio`` pedem o PDF de cada
    documento listado no processo.
    """


class OutputCpopgTRF1(OutputCnjConsultaBase, CamposProcessoPJe):
    """Uma linha do DataFrame de :meth:`TRF1Scraper.cpopg`.

    CNJ não encontrado ou cuja consulta falhou gera linha só com ``id_cnj``
    e ``motivo_falha`` (fora deste contrato). Herda ``extra="allow"`` de
    :class:`~juscraper.schemas.OutputCnjConsultaBase`.
    """
