"""Scraper for the Tribunal de Justica do Amapa (TJAP)."""
from typing import Union, List

import pandas as pd
import requests
from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_paginas, normalize_pesquisa
from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


class TJAPScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Amapa (TJAP).

    The TJAP uses the Tucujuris platform with a JSON REST API.
    Currently supports jurisprudence search (CJSG).
    """

    BASE_URL = "https://tucujuris.tjap.jus.br"

    def __init__(self):
        super().__init__("TJAP")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJAP."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJAP.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJAP."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJAP.")

    def cjsg(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        orgao: str = "0",
        numero_cnj: str | None = None,
        numero_acordao: str | None = None,
        numero_ano: str | None = None,
        palavras_exatas: bool = False,
        relator: str | None = None,
        secretaria: str | None = None,
        classe: str | None = None,
        votacao: str = "0",
        origem: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJAP jurisprudence.

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        orgao : str
            ``"0"`` for all (default), ``"tj"`` for Tribunal, ``"recursal"`` for Turma Recursal.
        numero_cnj : str, optional
            CNJ unique case number.
        numero_acordao : str, optional
            Decision number.
        numero_ano : str, optional
            Number/year (e.g. ``"001858/1999"``).
        palavras_exatas : bool
            If True, search for exact words.
        relator : str, optional
            Reporting judge name.
        secretaria : str, optional
            Court division.
        classe : str, optional
            Procedural class.
        votacao : str
            ``"0"`` for all (default), ``"Unanime"``, ``"Maioria"``.
        origem : str, optional
            Origin (comarca).

        Returns
        -------
        pd.DataFrame
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            orgao=orgao,
            numero_cnj=numero_cnj,
            numero_acordao=numero_acordao,
            numero_ano=numero_ano,
            palavras_exatas=palavras_exatas,
            relator=relator,
            secretaria=secretaria,
            classe=classe,
            votacao=votacao,
            origem=origem,
        )
        return self.cjsg_parse(brutos)

    def cjsg_download(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        orgao: str = "0",
        numero_cnj: str | None = None,
        numero_acordao: str | None = None,
        numero_ano: str | None = None,
        palavras_exatas: bool = False,
        relator: str | None = None,
        secretaria: str | None = None,
        classe: str | None = None,
        votacao: str = "0",
        origem: str | None = None,
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJAP.

        Parameters are the same as :meth:`cjsg`.

        Returns
        -------
        list
            List of raw JSON responses (one per page).
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        return cjsg_download_manager(
            pesquisa=pesquisa,
            paginas=paginas,
            session=self.session,
            orgao=orgao,
            numero_cnj=numero_cnj,
            numero_acordao=numero_acordao,
            numero_ano=numero_ano,
            palavras_exatas=palavras_exatas,
            relator=relator,
            secretaria=secretaria,
            classe=classe,
            votacao=votacao,
            origem=origem,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded CJSG JSON responses.

        Parameters
        ----------
        resultados_brutos : list
            List of raw JSON responses from the TJAP API.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
