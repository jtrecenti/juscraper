"""
Aggregators
~~~~~~~~~~~
Interface pública: jus.scrapers(<sigla>, **kwargs)

A implementação real de cada scraper mora em:
- juscraper.aggregators.<sigla_agregador>.client.<Nome>Scraper
"""

from .datajud import DatajudScraper
from .jusbr import JusbrScraper

__all__ = [
    "DatajudScraper",
    "JusbrScraper",
]
