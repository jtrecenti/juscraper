"""Agregadores; a interface pública é ``jus.scraper(<sigla>, **kwargs)``.

A implementação de cada raspador fica em
``juscraper.aggregators.<sigla_agregador>.client.<Nome>Scraper``.
"""

from .datajud import DatajudScraper
from .jusbr import JusbrScraper

__all__ = [
    "DatajudScraper",
    "JusbrScraper",
]
