"""Scraper for the Tribunal de Justiça de Mato Grosso do Sul (TJMS)."""
from .._esaj.acordao_cjsg import EsajAcordaoCjsgScraper


class TJMSScraper(EsajAcordaoCjsgScraper):
    """TJMS no eSAJ: ``cjsg`` e o PDF do acórdão por ``baixar_acordao``."""

    BASE_URL = "https://esaj.tjms.jus.br/"
    TRIBUNAL_NAME = "TJMS"
