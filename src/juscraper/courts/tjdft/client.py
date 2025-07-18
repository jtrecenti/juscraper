"""
Module for the scraper of the Court of Justice of the Federal District and Territories (TJDFT).
"""
from typing import Union, List
import pandas as pd
from juscraper.core.base import BaseScraper
from .download import cjsg_download
from .parse import cjsg_parse

class TJDFTScraper(BaseScraper):
    """Scraper for the Court of Justice of the Federal District and Territories (TJDFT)."""
    BASE_URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"

    def __init__(self):
        super().__init__("TJDFT")

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub for compatibility with BaseScraper."""
        raise NotImplementedError("TJDFT does not implement cpopg.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub for compatibility with BaseScraper."""
        raise NotImplementedError("TJDFT does not implement cposg.")

    def cjsg_download(
        self,
        query: str,
        paginas: Union[int, list, range] = 0,
        sinonimos: bool = True,
        espelho: bool = True,
        inteiro_teor: bool = False,
        quantidade_por_pagina: int = 10,
    ) -> list:
        """
        Downloads raw search results from the TJDFT jurisprudence search (using requests).
        Returns a list of raw results (JSON).
        """
        return cjsg_download(
            query=query,
            paginas=paginas,
            sinonimos=sinonimos,
            espelho=espelho,
            inteiro_teor=inteiro_teor,
            quantidade_por_pagina=quantidade_por_pagina,
            base_url=self.BASE_URL
        )

    def cjsg_parse(self, resultados_brutos: list) -> list:
        """
        Extracts structured information from the raw TJDFT search results.
        Returns all fields present in each item.
        """
        return cjsg_parse(resultados_brutos)

    def cjsg(self, query: str, paginas: Union[int, list, range] = 0) -> pd.DataFrame:
        """
        Searches for TJDFT jurisprudence in a simplified way (download + parse).
        Returns a ready-to-analyze DataFrame.
        """
        brutos = self.cjsg_download(query=query, paginas=paginas)
        dados = self.cjsg_parse(brutos)
        df = pd.DataFrame(dados)
        for col in ["data_julgamento", "data_publicacao"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df
