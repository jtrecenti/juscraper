# read version from installed package

"""Juscraper: A package for scraping legal data."""

from importlib.metadata import version
from .tribunal_manager import scraper

__version__ = version("juscraper")

__all__ = ["scraper"]
