"""Scraper for the Tribunal de Justiça de Mato Grosso do Sul (TJMS)."""
from .._esaj.acordao_cjsg import EsajAcordaoCjsgScraper
from .._esaj.cjpg import EsajCjpgScraper


class TJMSScraper(EsajCjpgScraper, EsajAcordaoCjsgScraper):
    """TJMS no eSAJ: ``cjsg``, ``cjpg``, o PDF do acórdão (``baixar_acordao``) e o da sentença (``baixar_sentenca``)."""

    BASE_URL = "https://esaj.tjms.jus.br/"
    TRIBUNAL_NAME = "TJMS"
