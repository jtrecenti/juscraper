"""
Gerencia e retorna o scraper apropriado para cada tribunal suportado.
"""
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
    if tribunal_name == "TJRS":
        return TJRSScraper()
    if tribunal_name == "TJPR":
        return TJPRScraper()
    if tribunal_name == "JUSBR":
        return JusbrScraper(**kwargs)
    if tribunal_name == "DATAJUD":
        return DatajudScraper(**kwargs)
    if tribunal_name == "TJDFT":
        return TJDFTScraper()
    raise ValueError(f"Tribunal '{tribunal_name}' ainda não é suportado.")
