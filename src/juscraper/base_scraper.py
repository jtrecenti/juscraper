"""Base scraper class for court data extraction."""
from abc import ABC, abstractmethod
import os
import tempfile
from typing import Union, List

class BaseScraper(ABC):
    """Classe base para raspadores de tribunais."""

    def __init__(self, tribunal_name: str):
        self.tribunal_name = tribunal_name
        self.verbose = 0
        self.download_path = None

    @abstractmethod
    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Busca um processo na consulta de processos originários do primeiro grau."""

    @abstractmethod
    def cposg(self, id_cnj: Union[str, List[str]]):
        """Busca um processo na consulta de processos originários do segundo grau."""

    @abstractmethod
    def cjsg(self, query: str):
        """Busca jurisprudência na consulta de julgados do segundo grau."""

    def set_verbose(self, verbose: int):
        """Seta o nível de verbosidade do scraper.

        Args:
            verbose (int): Verbosity level.
        """
        self.verbose = verbose

    def set_download_path(self, path: str):
        """Define o caminho de download. Se None, cria um diretório temporário."""
        # if path is None, define a default path in the temp directory
        if path is None:
            path = tempfile.mkdtemp()
        # check if path is a valid directory. If it is not, create it
        if not os.path.isdir(path):
            if self.verbose:
                print(
                    f"O caminho de download '{path}' nao é um diretório. Criando esse diretório..."
                )
            os.makedirs(path)
        self.download_path = path
        if self.verbose:
            print(f"Caminho de download definido como '{path}'.")
