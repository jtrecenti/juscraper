"""Scraper for the Tribunal Regional Federal da 1ª Região (TRF1).

Wraps the PJe public-consultation system at
``pje1g-consultapublica.trf1.jus.br/consultapublica/``. The form layout
mirrors TRF3 (autocomplete ``classeJudicial`` + ``dataAutuacaoDecoration``
block), so the search payload shape is shared down to the field names; the
divergence lives entirely in :data:`BASE_URL`. All the search/detail/movs
logic lives in :class:`juscraper.courts._trf.base.TRFConsultaScraper`.
"""
from __future__ import annotations

from .._trf.base import TRFConsultaScraper


class TRF1Scraper(TRFConsultaScraper):
    """TRF1 PJe consulta pública (1º grau)."""

    BASE_URL = "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"
    TRIBUNAL_NAME = "TRF1"
