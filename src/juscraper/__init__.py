# read version from installed package
from importlib.metadata import version
from .tribunal_manager import scraper

__version__ = version("juscraper")

__all__ = ["scraper"]
