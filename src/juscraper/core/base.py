"""
Base scraper class for court data extraction.
"""
from abc import ABC
import os
import tempfile
import logging
from typing import Optional

logger = logging.getLogger("juscraper.core.base")

class BaseScraper(ABC):
    """Base scraper class for court data extraction."""

    # Subclasses devem chamar `set_download_path` (ou atribuir diretamente)
    # em `__init__`; por isso o atributo é tipado como `str`, sem default.
    download_path: str

    def __init__(self, tribunal_name: str):
        self.tribunal_name = tribunal_name
        self.verbose = 0
        self.download_path = ""

    def set_verbose(self, verbose: int):
        """Set the verbosity level of the scraper.

        Args:
            verbose (int): Verbosity level.
        """
        self.verbose = verbose

    def set_download_path(self, path: Optional[str]) -> None:
        """Set the download path. If None, creates a temporary directory."""
        if path is None:
            path = tempfile.mkdtemp()
        if not os.path.isdir(path):
            if self.verbose:
                logger.info(
                    "O caminho de download '%s' não é um diretório. Criando esse diretório...",
                    path
                )
            os.makedirs(path)
        self.download_path = path
        if self.verbose:
            logger.info(
                "Caminho de download definido como '%s'.",
                path
            )
