from abc import ABC, abstractmethod

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
