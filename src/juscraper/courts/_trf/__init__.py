"""Shared infrastructure for the TRF PJe ConsultaPública scrapers (refs #84, #294).

Internal package — prefix ``_`` signals that nothing here is public API.
TRF1, TRF5 and TJPE (1º grau) consume :class:`TRFConsultaScraper` to avoid
near-duplicate search + detail + movs/docs pagination + HTML parse code
across the PJe ConsultaPública JSF deployments. TRF3 left the family when its
public consultation moved to a JSON API (see :mod:`juscraper.courts.trf3`).
"""
from .base import TRFConsultaScraper

__all__ = ["TRFConsultaScraper"]
