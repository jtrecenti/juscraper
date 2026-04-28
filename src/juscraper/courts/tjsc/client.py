"""Scraper for the Tribunal de Justica de Santa Catarina (TJSC)."""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_datas, normalize_paginas, normalize_pesquisa

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


class TJSCScraper(BaseScraper):
    """Scraper for the Tribunal de Justica de Santa Catarina (TJSC).

    Uses the eproc jurisprudence search at eproc1g.tjsc.jus.br.
    """

    BASE_URL = "https://eproc1g.tjsc.jus.br"

    def __init__(self):
        super().__init__("TJSC")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJSC."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJSC.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJSC."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJSC.")

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        campo: str = "E",
        processo: str = "",
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJSC jurisprudence.

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        campo : str, optional
            Search field: ``"E"`` for ementa (default), ``"I"`` for inteiro teor.
        processo : str, optional
            Process number filter.

        Returns
        -------
        pd.DataFrame
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(**kwargs)
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            campo=campo,
            processo=processo,
            dt_decisao_inicio=datas["data_julgamento_inicio"] or "",
            dt_decisao_fim=datas["data_julgamento_fim"] or "",
            dt_publicacao_inicio=datas["data_publicacao_inicio"] or "",
            dt_publicacao_fim=datas["data_publicacao_fim"] or "",
        )
        return self.cjsg_parse(brutos)

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> list:
        """Download raw HTML pages from TJSC.

        Returns
        -------
        list
            List of raw HTML strings (one per page).
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        return cjsg_download_manager(
            pesquisa=pesquisa,
            paginas=paginas,
            session=self.session,
            **{k: v for k, v in kwargs.items() if k not in ("query", "termo")},
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded HTML pages.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
