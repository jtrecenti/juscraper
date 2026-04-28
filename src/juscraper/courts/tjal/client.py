"""Scraper for the Tribunal de Justiça de Alagoas (TJAL)."""
from .._esaj.base import EsajSearchScraper


class TJALScraper(EsajSearchScraper):
    """TJAL uses the eSAJ platform; ``cjsg`` is the only endpoint supported."""

    BASE_URL = "https://www2.tjal.jus.br/"
    TRIBUNAL_NAME = "TJAL"
