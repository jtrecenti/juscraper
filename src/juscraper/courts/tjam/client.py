"""Scraper for the Tribunal de Justiça do Amazonas (TJAM)."""
from .._esaj.base import EsajSearchScraper


class TJAMScraper(EsajSearchScraper):
    """TJAM uses the eSAJ platform; ``cjsg`` is the only endpoint supported."""

    BASE_URL = "https://consultasaj.tjam.jus.br/"
    TRIBUNAL_NAME = "TJAM"
