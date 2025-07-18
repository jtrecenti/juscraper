"""
juscraper
~~~~~~~~~
Interface pública: jus.scraper(<sigla>, **kwargs)

A implementação real de cada scraper mora em:
- juscraper.courts.<sigla_tribunal>.client.TJ<sigla_tribunal>Scraper
- juscraper.aggregators.<sigla_agregador>.client.<Nome>Scraper
"""
from importlib import import_module
from typing import Any
from importlib.metadata import version

# Mapeia a sigla que o usuário digita →  caminho do módulo e classe
_SCRAPERS: dict[str, str] = {
    # Courts
    "tjsp":  "juscraper.courts.tjsp.client:TJSPScraper",
    "tjdft": "juscraper.courts.tjdft.client:TJDFTScraper",
    "tjrs":  "juscraper.courts.tjrs.client:TJRSScraper",
    "tjpr":  "juscraper.courts.tjpr.client:TJPRScraper",
    # Aggregators
    "datajud": "juscraper.aggregators.datajud.client:DatajudScraper",
    "jusbr": "juscraper.aggregators.jusbr.client:JusbrScraper",
    # acrescente outros aqui ou carregue dinamicamente via entry-points
}

def scraper(sigla: str, *args: Any, **kwargs: Any):
    """
    Factory que devolve o scraper correto.

    Exemplos
    --------
    >>> import juscraper as jus
    >>> tjsp = jus.scraper("tjsp")
    >>> jusbr = jus.scraper("jusbr")
    """
    sigla = sigla.lower()
    if sigla not in _SCRAPERS:
        raise ValueError(
            f"Scraper '{sigla}' não suportado. Disponíveis: {', '.join(_SCRAPERS)}"
        )
    path, cls_name = _SCRAPERS[sigla].split(":")
    mod = import_module(path)        # importa só quando é pedido (lazy)
    cls = getattr(mod, cls_name)     # recupera a classe
    return cls(*args, **kwargs)      # instancia e devolve

__version__ = version("juscraper")
__all__ = ["scraper"]
