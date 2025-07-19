"""
Gerencia e retorna o scraper apropriado para cada tribunal suportado.
"""
from .tjsp_scraper import TJSPScraper
from .tjrs_scraper import TJRSScraper
from .jusbr_scraper import JusbrScraper
from .datajud_scraper import DatajudScraper
from .tjpr_scraper import TJPRScraper
from .tjdft_scraper import TJDFTScraper

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
    else:
        raise ValueError(f"Tribunal '{tribunal_name}' ainda não é suportado.")
