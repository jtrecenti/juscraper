"""
juscraper
~~~~~~~~~
Public interface: jus.scraper(<sigla>, **kwargs)

The real implementation of each scraper is in:
- juscraper.courts.<sigla_tribunal>.client.TJ<sigla_tribunal>Scraper
- juscraper.aggregators.<sigla_agregador>.client.<Nome>Scraper
"""
from importlib import import_module
from typing import Any
from importlib.metadata import version

_SCRAPERS: dict[str, str] = {
    "tjsp":  "juscraper.courts.tjsp.client:TJSPScraper",
    "tjdft": "juscraper.courts.tjdft.client:TJDFTScraper",
    "tjrs":  "juscraper.courts.tjrs.client:TJRSScraper",
    "tjpr":  "juscraper.courts.tjpr.client:TJPRScraper",
    "datajud": "juscraper.aggregators.datajud.client:DatajudScraper",
    "jusbr": "juscraper.aggregators.jusbr.client:JusbrScraper",
}

def scraper(sigla: str, *args: Any, **kwargs: Any):
    """
    Factory that returns the correct scraper.

    Examples
    --------
    >>> import juscraper as jus
    >>> tjsp = jus.scraper("tjsp")
    >>> jusbr = jus.scraper("jusbr")
    """
    sigla = sigla.lower()
    if sigla not in _SCRAPERS:
        raise ValueError(
            f"Scraper '{sigla}' not supported. Available: {', '.join(_SCRAPERS)}"
        )
    path, cls_name = _SCRAPERS[sigla].split(":")
    mod = import_module(path)
    cls = getattr(mod, cls_name)
    return cls(*args, **kwargs)

__version__ = version("juscraper")
__all__ = ["scraper"]
