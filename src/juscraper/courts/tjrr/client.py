"""Scraper for the Tribunal de Justica de Roraima (TJRR)."""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_datas, normalize_paginas, normalize_pesquisa

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


class TJRRScraper(BaseScraper):
    """Scraper for the Tribunal de Justica de Roraima (TJRR).

    Uses the JSF/PrimeFaces-based jurisprudence search at jurisprudencia.tjrr.jus.br.
    """

    BASE_URL = "https://jurisprudencia.tjrr.jus.br"

    def __init__(self):
        super().__init__("TJRR")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJRR."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJRR.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJRR."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJRR.")

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        relator: str = "",
        orgao_julgador: list | None = None,
        especie: list | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJRR jurisprudence.

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        relator : str, optional
            Reporter judge name.
        orgao_julgador : list, optional
            Judging body codes (e.g. ``["PRIMEIRA_TURMA_CIVEL", "CAMARA_CRIMINAL"]``).
        especie : list, optional
            Decision type codes.

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
            relator=relator,
            data_inicio=datas["data_julgamento_inicio"] or "",
            data_fim=datas["data_julgamento_fim"] or "",
            orgao_julgador=orgao_julgador,
            especie=especie,
        )
        return self.cjsg_parse(brutos)

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> list:
        """Download raw HTML pages from TJRR.

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
