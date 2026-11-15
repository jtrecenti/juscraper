"""Scraper for the Tribunal de Justiça do Ceará (TJCE)."""
import requests

from .._esaj.acordao_cjsg import EsajAcordaoCjsgScraper
from ._tls import _TJCETLSAdapter


class TJCEScraper(EsajAcordaoCjsgScraper):
    """TJCE usa o eSAJ com adaptador TLS (SECLEVEL=1).

    O inteiro teor do acórdão sai direto do ``cd_acordao`` do cjsg
    (``cjsg/getArquivo.do``), sem login e sem captcha (sonda de 2026-11); ver
    :mod:`juscraper.courts._esaj.acordao_cjsg`.
    """

    BASE_URL = "https://esaj.tjce.jus.br/"
    TRIBUNAL_NAME = "TJCE"

    def _configure_session(self, session: requests.Session) -> None:
        session.mount("https://", _TJCETLSAdapter())
