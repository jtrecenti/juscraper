"""Shared infrastructure for eSAJ-family cjsg scrapers (refs #84).

Internal package — prefix ``_`` signals that nothing here is public API.
Court clients consume :class:`EsajSearchScraper` to avoid ~2800 lines of
near-duplicate POST+GET paginated download + HTML parse code across the
six eSAJ courts (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP).
"""
from .base import EsajSearchScraper
from .forms import build_cjsg_form_body
from .parse import cjsg_n_pags, cjsg_parse_manager

__all__ = [
    "EsajSearchScraper",
    "build_cjsg_form_body",
    "cjsg_n_pags",
    "cjsg_parse_manager",
]
