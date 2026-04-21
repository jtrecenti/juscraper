"""Scraper for the Tribunal de Justiça do Ceará (TJCE)."""
import requests

from .._esaj.base import EsajSearchScraper
from ._tls import _TJCETLSAdapter


class TJCEScraper(EsajSearchScraper):
    """TJCE uses the eSAJ platform with a TLS adapter (SECLEVEL=1)."""

    BASE_URL = "https://esaj.tjce.jus.br/"
    TRIBUNAL_NAME = "TJCE"

    def _configure_session(self, session: requests.Session) -> None:
        session.mount("https://", _TJCETLSAdapter())
