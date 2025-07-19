"""
Scraper for the Tribunal de Justiça do Rio Grande do Sul (TJRS).
"""
from typing import Union, List
import requests
import pandas as pd
from juscraper.core.base import BaseScraper
from .download import cjsg_download_manager
from .parse import cjsg_parse_manager

class TJRSScraper(BaseScraper):
    """Scraper for the Tribunal de Justiça do Rio Grande do Sul."""

    BASE_URL = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"
    DEFAULT_PARAMS = {
        "tipo-busca": "jurisprudencia-mob",
        "client": "tjrs_index",
        "proxystylesheet": "tjrs_index",
        "lr": "lang_pt",
        "oe": "UTF-8",
        "ie": "UTF-8",
        "getfields": "*",
        "filter": "0",
        "entqr": "3",
        "content": "body",
        "accesskey": "p",
        "ulang": "",
        "entqrm": "0",
        "ud": "1",
        "start": "0",
        "aba": "jurisprudencia",
        "sort": "date:D:L:d1"
    }

    def __init__(self):
        super().__init__("TJRS")
        self.session = requests.Session()

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """
        Fetches jurisprudence from TJRS in a simplified way (download + parse).
        Returns a DataFrame ready for analysis.
        """
        print(f"[TJRS] Consulting process: {id_cnj}")
        # Real implementation of the search here

    def cposg(self, id_cnj: Union[str, List[str]]):
        """
        Fetches jurisprudence from TJRS in a simplified way (download + parse).
        Returns a DataFrame ready for analysis.
        """
        print(f"[TJRS] Consulting process: {id_cnj}")
        # Real implementation of the search here

    def cjsg_download(
        self,
        termo: str,
        paginas: Union[int, list, range] = 1,
        classe: str = None,
        assunto: str = None,
        orgao_julgador: str = None,
        relator: str = None,
        data_julgamento_de: str = None,
        data_julgamento_ate: str = None,
        data_publicacao_de: str = None,
        data_publicacao_ate: str = None,
        tipo_processo: str = None,
        secao: str = None,
        session: 'requests.Session' = None,
        **kwargs
    ) -> list:
        """
        Downloads raw results from the TJRS 'jurisprudence search' (multiple pages).
        Returns a list of raw results (JSON).
        New parameter: secao ('civel', 'crime', or None)
        """
        if session is None:
            session = self.session
        return cjsg_download_manager(
            termo=termo,
            paginas=paginas,
            classe=classe,
            assunto=assunto,
            orgao_julgador=orgao_julgador,
            relator=relator,
            data_julgamento_de=data_julgamento_de,
            data_julgamento_ate=data_julgamento_ate,
            data_publicacao_de=data_publicacao_de,
            data_publicacao_ate=data_publicacao_ate,
            tipo_processo=tipo_processo,
            secao=secao,
            session=session,
            **kwargs
        )

    def cjsg_parse(self, resultados_brutos: list) -> 'pd.DataFrame':
        """
        Extracts relevant data from the raw results returned by TJRS.
        Returns a DataFrame with the decisions.
        """
        return cjsg_parse_manager(resultados_brutos)

    def cjsg(
        self,
        query: str,
        paginas: Union[int, list, range] = 1,
        classe: str = None,
        assunto: str = None,
        orgao_julgador: str = None,
        relator: str = None,
        data_julgamento_de: str = None,
        data_julgamento_ate: str = None,
        data_publicacao_de: str = None,
        data_publicacao_ate: str = None,
        tipo_processo: str = None,
        secao: str = None,
        session: 'requests.Session' = None,
        **kwargs
    ) -> 'pd.DataFrame':
        """
        Fetches jurisprudence from TJRS in a simplified way (download + parse).
        New parameter: secao ('civel', 'crime', or None)
        Returns a ready-to-analyze DataFrame.
        """
        brutos = self.cjsg_download(
            termo=query,
            paginas=paginas,
            classe=classe,
            assunto=assunto,
            orgao_julgador=orgao_julgador,
            relator=relator,
            data_julgamento_de=data_julgamento_de,
            data_julgamento_ate=data_julgamento_ate,
            data_publicacao_de=data_publicacao_de,
            data_publicacao_ate=data_publicacao_ate,
            tipo_processo=tipo_processo,
            secao=secao,
            session=session,
            **kwargs
        )
        return self.cjsg_parse(brutos)
