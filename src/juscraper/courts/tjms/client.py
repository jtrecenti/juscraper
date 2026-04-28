"""Scraper for the Tribunal de Justiça de Mato Grosso do Sul (TJMS)."""
from .._esaj.base import EsajSearchScraper


class TJMSScraper(EsajSearchScraper):
    """TJMS uses the eSAJ platform; ``cjsg`` is the only endpoint supported."""

    BASE_URL = "https://esaj.tjms.jus.br/"
    TRIBUNAL_NAME = "TJMS"
