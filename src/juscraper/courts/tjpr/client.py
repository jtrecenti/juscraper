"""
Scraper for the Court of Justice of Paraná (TJPR).
"""
from typing import Optional, Union, List
import requests
import pandas as pd
from juscraper.core.base import BaseScraper
from .download import cjsg_download, get_initial_tokens
from .parse import cjsg_parse

class TJPRScraper(BaseScraper):
    """Scraper for the Court of Justice of Paraná."""

    BASE_URL = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?actionType=pesquisar"
    HOME_URL = "https://portal.tjpr.jus.br/jurisprudencia/"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
    )

    def __init__(self):
        super().__init__("TJPR")
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.jsessionid: Optional[str] = None

    def cjsg_download(self, termo: str, paginas: Union[int, list, range] = 1,
                      data_julgamento_de: str = None, data_julgamento_ate: str = None,
                      data_publicacao_de: str = None, data_publicacao_ate: str = None) -> list:
        """
        Downloads raw results from the TJPR jurisprudence search (multiple pages).
        Returns a list of HTMLs (one per page).
        """
        return cjsg_download(
            self.session, self.USER_AGENT, self.HOME_URL, termo, paginas,
            data_julgamento_de, data_julgamento_ate, data_publicacao_de, data_publicacao_ate
        )

    def cjsg_parse(self, resultados_brutos: list, criterio: str = None) -> pd.DataFrame:
        """
        Extracts relevant data from the HTMLs returned by TJPR.
        Returns a DataFrame with the decisions.
        """
        # For complete minutes, you need to pass session, jsessionid, user_agent
        jsessionid, _ = get_initial_tokens(self.session, self.HOME_URL)
        return cjsg_parse(resultados_brutos, criterio, self.session, jsessionid, self.USER_AGENT)

    def cjsg(self, query: str, paginas: Union[int, list, range] = 1,
             data_julgamento_de: str = None, data_julgamento_ate: str = None,
             data_publicacao_de: str = None, data_publicacao_ate: str = None, **kwargs) -> pd.DataFrame:
        """
        Searches for TJPR jurisprudence in a simplified way (download + parse).
        Returns a ready-to-analyze DataFrame.
        """
        brutos = self.cjsg_download(
            termo=query,
            paginas=paginas,
            data_julgamento_de=data_julgamento_de,
            data_julgamento_ate=data_julgamento_ate,
            data_publicacao_de=data_publicacao_de,
            data_publicacao_ate=data_publicacao_ate,
            **kwargs
        )
        return self.cjsg_parse(brutos, query)

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: Primeiro grau case consultation not implemented for TJPR."""
        raise NotImplementedError("Consulta de processos de 1º grau não implementada para TJPR.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: Segundo grau case consultation not implemented for TJPR."""
        raise NotImplementedError("Consulta de processos de 2º grau não implementada para TJPR.")
