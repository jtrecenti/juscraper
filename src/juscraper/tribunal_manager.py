"""Gerencia e retorna o scraper apropriado para cada tribunal suportado."""
from .courts.cnj.client import ComunicaCNJ
from .datajud_scraper import DatajudScraper
from .jusbr_scraper import JusbrScraper
from .tjdft_scraper import TJDFTScraper
from .tjpr_scraper import TJPRScraper
from .tjrs_scraper import TJRSScraper
from .tjsp_scraper import TJSPScraper


def scraper(tribunal_name: str, **kwargs):
    """Retorna o raspador correspondente ao tribunal solicitado."""
    tribunal_name = tribunal_name.upper()

    if tribunal_name == "TJSP":
        return TJSPScraper(**kwargs)
    elif tribunal_name == "TJRS":
        return TJRSScraper()
    elif tribunal_name == "TJPR":
        return TJPRScraper()
    elif tribunal_name == "JUSBR":
        return JusbrScraper(**kwargs)
    elif tribunal_name == "DATAJUD":
        return DatajudScraper(**kwargs)
    elif tribunal_name == "TJDFT":
        return TJDFTScraper()
    elif tribunal_name == "CNJ":
        return ComunicaCNJ()
    else:
        raise ValueError(f"Tribunal '{tribunal_name}' ainda não é suportado.")
