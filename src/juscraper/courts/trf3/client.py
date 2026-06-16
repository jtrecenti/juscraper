"""Scraper for the Tribunal Regional Federal da 3ª Região (TRF3).

Wraps the PJe public-consultation system at ``pje1g.trf3.jus.br/pje/``. The
TRF3 deployment sits behind an Akamai bot manager (``ak_bmsc`` cookie) which
silently drops connections that don't carry a realistic browser header set;
the ``BROWSER_HEADERS`` applied by
:meth:`juscraper.courts._trf.base.TRFConsultaScraper._configure_session` are
tuned to pass that challenge. The form layout matches TRF1 (autocomplete
``classeJudicial`` + ``dataAutuacaoDecoration``), so only :data:`BASE_URL`
diverges.
"""
from __future__ import annotations

from .._trf.base import TRFConsultaScraper


class TRF3Scraper(TRFConsultaScraper):
    """TRF3 PJe consulta pública (1º grau)."""

    BASE_URL = "https://pje1g.trf3.jus.br/pje/"
    TRIBUNAL_NAME = "TRF3"
