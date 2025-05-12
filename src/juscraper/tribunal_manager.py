from .tjsp_scraper import TJSP_Scraper
from .tjrs_scraper import TJRS_Scraper
from .comunicaCNJ_scraper import comunicaCNJ_Scraper
from .jusbr_scraper import JUSBR_Scraper

def scraper(tribunal_name: str, **kwargs):
    """Retorna o raspador correspondente ao tribunal solicitado."""
    tribunal_name = tribunal_name.upper()
    
    if tribunal_name == "TJSP":
        return TJSP_Scraper(**kwargs)
    elif tribunal_name == "TJRS":
        return TJRS_Scraper()
    elif tribunal_name == 'COMUNICA_CNJ':
        return comunicaCNJ_Scraper(**kwargs)
    elif tribunal_name == "TJPR":
        return TJPR_Scraper()
    elif tribunal_name == "JUSBR":
        return JUSBR_Scraper(**kwargs)
    else:
        raise ValueError(f"Tribunal '{tribunal_name}' ainda não é suportado.")
