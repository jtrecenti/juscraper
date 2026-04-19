"""Scraper for the Tribunal de Justica do Piaui (TJPI)."""
from typing import Union, List

import pandas as pd
import requests
from juscraper.core.base import BaseScraper
from juscraper.utils.params import (
    normalize_datas,
    normalize_paginas,
    normalize_pesquisa,
    to_iso_date,
)
from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


class TJPIScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Piaui (TJPI).

    Uses the JusPI search interface at jurisprudencia.tjpi.jus.br.
    Results are HTML-based (server-rendered) and parsed with BeautifulSoup.
    """

    BASE_URL = "https://jurisprudencia.tjpi.jus.br"

    def __init__(self):
        super().__init__("TJPI")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJPI."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJPI.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJPI."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJPI.")

    def cjsg(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        tipo: str = "",
        relator: str = "",
        classe: str = "",
        orgao: str = "",
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJPI jurisprudence.

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        tipo : str, optional
            Decision type. Options: ``"Acordao"``, ``"Decisao Terminativa"``, ``"Sumula"``.
        relator : str, optional
            Reporter judge name (must match dropdown value exactly).
        classe : str, optional
            Procedural class (must match dropdown value exactly).
        orgao : str, optional
            Judging body (must match dropdown value exactly).

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
            tipo=tipo,
            relator=relator,
            classe=classe,
            orgao=orgao,
            data_min=to_iso_date(datas["data_julgamento_inicio"]) or "",
            data_max=to_iso_date(datas["data_julgamento_fim"]) or "",
        )
        return self.cjsg_parse(brutos)

    def cjsg_download(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> list:
        """Download raw HTML pages from TJPI.

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
