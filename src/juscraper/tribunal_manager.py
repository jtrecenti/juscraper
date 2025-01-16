from .tjsp_scraper import TJSP_Scraper
from .tjrs_scraper import TJRS_Scraper

def scraper(tribunal_name: str, **kwargs):
    """Retorna o raspador correspondente ao tribunal solicitado."""
    tribunal_name = tribunal_name.upper()
    
    if tribunal_name == "TJSP":
        return TJSP_Scraper(**kwargs)
    elif tribunal_name == "TJRS":
        return TJRS_Scraper()
    else:
        raise ValueError(f"Tribunal '{tribunal_name}' ainda não é suportado.")
