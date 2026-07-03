"""Shared infrastructure for the TRF PJe ConsultaPública scrapers (refs #84, #294).

Internal package — prefix ``_`` signals that nothing here is public API.
TRF1/TRF3/TRF5 consume :class:`TRFConsultaScraper` to avoid ~2100 lines of
near-duplicate search + detail + movs/docs pagination + HTML parse code
across the three PJe ConsultaPública deployments.
"""
from .base import TRFConsultaScraper

__all__ = ["TRFConsultaScraper"]
