"""Scraper for the Tribunal de Justiça do Acre (TJAC)."""
from .._esaj.acordao import EsajAcordaoScraper


class TJACScraper(EsajAcordaoScraper):
    """TJAC uses the eSAJ platform: ``cjsg`` and the acórdão PDF via ``baixar_acordao``."""

    BASE_URL = "https://esaj.tjac.jus.br/"
    TRIBUNAL_NAME = "TJAC"
    CPOSG_PATH = "cposg5/"
    TIPOS_DOCUMENTO_ACORDAO = frozenset({"Acórdão", "Embargos de Declaração"})
