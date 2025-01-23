from abc import ABC, abstractmethod
import os

class BaseScraper(ABC):
    """Classe base para raspadores de tribunais."""

    def __init__(self, tribunal_name: str):
        self.tribunal_name = tribunal_name

    @abstractmethod
    def cpopg(self, process_number: str):
        """Busca um processo na consulta de processos originários do primeiro grau."""
        pass
    
    @abstractmethod
    def cposg(self, process_number: str):
        """Busca um processo na consulta de processos originários do segundo grau."""
        pass

    @abstractmethod
    def cjsg(self, query: str):
        """Busca jurisprudência na consulta de julgados do segundo grau."""
        pass

    def set_verbose(self, verbose: int):
        self.verbose = verbose

    def set_download_path(self, path: str):
        # if path is None, define a default path in the temp directory
        if path is None:
            path = tempfile.mkdtemp()
        # check if path is a valid directory. If it is not, create it
        if not os.path.isdir(path):
            if self.verbose:
                print(f"O caminho de download '{path}' nao é um diretório. Criando esse diretório...")
            os.makedirs(path)
        self.download_path = path
        if self.verbose:
            print(f"Caminho de download definido como '{path}'.")
