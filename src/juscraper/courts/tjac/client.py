"""Scraper for the Tribunal de Justiça do Acre (TJAC)."""
from .._esaj.base import EsajSearchScraper


class TJACScraper(EsajSearchScraper):
    """TJAC uses the eSAJ platform; ``cjsg`` is the only endpoint supported."""

    BASE_URL = "https://esaj.tjac.jus.br/"
    TRIBUNAL_NAME = "TJAC"
