"""
Scraper for the Court of Justice of Paraná (TJPR).
"""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, normalize_datas, normalize_paginas, normalize_pesquisa

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
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        brutos: list = cjsg_download(
            self.session, self.USER_AGENT, self.HOME_URL, pesquisa, paginas,
            datas["data_julgamento_inicio"], datas["data_julgamento_fim"],
            datas["data_publicacao_inicio"], datas["data_publicacao_fim"],
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
        """
        pesquisa_val = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        # Re-inject explicit date args into kwargs so the pipeline can resolve
        # aliases (data_inicio/data_fim) and canonical names in a single pass.
        for _date_key, _date_val in (
            ("data_julgamento_inicio", data_julgamento_inicio),
            ("data_julgamento_fim", data_julgamento_fim),
            ("data_publicacao_inicio", data_publicacao_inicio),
            ("data_publicacao_fim", data_publicacao_fim),
        ):
            if _date_val is not None:
                kwargs[_date_key] = _date_val
        inp = apply_input_pipeline_search(
            InputCJSGTJPR,
            "TJPRScraper.cjsg()",
            pesquisa=pesquisa_val,
            paginas=paginas,
            kwargs=kwargs,
        )
        brutos = self.cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
        )
        return self.cjsg_parse(brutos, inp.pesquisa)

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: Primeiro grau case consultation not implemented for TJPR."""
        raise NotImplementedError("Consulta de processos de 1º grau não implementada para TJPR.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: Segundo grau case consultation not implemented for TJPR."""
        raise NotImplementedError("Consulta de processos de 2º grau não implementada para TJPR.")
