"""
Scraper for the Court of Justice of Paraná (TJPR).
"""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import SEARCH_ALIASES, apply_input_pipeline_search, normalize_pesquisa

from .download import cjsg_download, get_initial_tokens
from .parse import cjsg_parse
from .schemas import InputCJSGTJPR


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

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        data_publicacao_inicio: Optional[str] = None,
        data_publicacao_fim: Optional[str] = None,
        **kwargs,
    ) -> list:
        """
        Downloads raw results from the TJPR jurisprudence search (multiple pages).
        Returns a list of HTMLs (one per page).

        Args:
            pesquisa: Search term. ``termo`` is accepted as deprecated alias.
            paginas (int, list, range, or None): Pages to download (1-based).
                int: paginas=3 downloads pages 1-3.
                range: range(1, 4) downloads pages 1-3.
                None: downloads all available pages.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJPR,
            "TJPRScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
        )
        brutos: list = cjsg_download(
            self.session, self.USER_AGENT, self.HOME_URL, inp.pesquisa, inp.paginas,
            inp.data_julgamento_inicio, inp.data_julgamento_fim,
            inp.data_publicacao_inicio, inp.data_publicacao_fim,
        )
        return brutos

    def cjsg_parse(self, resultados_brutos: list, criterio: Optional[str] = None) -> pd.DataFrame:
        """
        Extracts relevant data from the HTMLs returned by TJPR.
        Returns a DataFrame with the decisions.
        """
        jsessionid, _ = get_initial_tokens(self.session, self.HOME_URL)
        return cjsg_parse(resultados_brutos, criterio, self.session, jsessionid, self.USER_AGENT)

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        data_publicacao_inicio: Optional[str] = None,
        data_publicacao_fim: Optional[str] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Searches for TJPR jurisprudence in a simplified way (download + parse).
        Returns a ready-to-analyze DataFrame.

        See also:
            :class:`juscraper.courts.tjpr.schemas.InputCJSGTJPR` — schema
            pydantic e a fonte da verdade dos filtros aceitos via ``**kwargs``.
        """
        # Resolve search alias here so cjsg_parse receives the actual term
        # for inteiro-teor lookups. Strip apenas SEARCH_ALIASES (query/termo)
        # para evitar re-pass duplicado; date aliases (data_inicio/data_fim,
        # *_de/*_ate) seguem em kwargs e sao normalizados pelo pipeline em
        # cjsg_download via normalize_datas.
        pesquisa_resolved = normalize_pesquisa(pesquisa, **kwargs)
        for alias in SEARCH_ALIASES:
            kwargs.pop(alias, None)
        brutos = self.cjsg_download(
            pesquisa=pesquisa_resolved,
            paginas=paginas,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        return self.cjsg_parse(brutos, pesquisa_resolved)

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: Primeiro grau case consultation not implemented for TJPR."""
        raise NotImplementedError("Consulta de processos de 1º grau não implementada para TJPR.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: Segundo grau case consultation not implemented for TJPR."""
        raise NotImplementedError("Consulta de processos de 2º grau não implementada para TJPR.")
