"""Scraper for the Tribunal de Justiça do Acre (TJAC)."""
from typing import ClassVar

from .._esaj.acordao import EsajAcordaoScraper


class TJACScraper(EsajAcordaoScraper):
    """TJAC uses the eSAJ platform: ``cjsg`` and the acórdão PDF via ``baixar_acordao``."""

    BASE_URL = "https://esaj.tjac.jus.br/"
    TRIBUNAL_NAME = "TJAC"
    # ``cposg/`` responde 503 no TJAC; a consulta de 2º grau mora em ``cposg5/``.
    CPOSG_PATH = "cposg5/"
    # O TJAC tipa o acórdão de embargos pelo recurso, e não como "Acórdão".
    TIPOS_DOCUMENTO_ACORDAO: ClassVar[frozenset[str]] = frozenset({"Acórdão", "Embargos de Declaração"})
