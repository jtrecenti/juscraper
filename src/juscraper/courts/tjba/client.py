"""
Scraper for the Tribunal de Justica do Estado da Bahia (TJBA).
"""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJBA


class TJBAScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Estado da Bahia."""

    BASE_URL = "https://jurisprudenciaws.tjba.jus.br/graphql"

    def __init__(self):
        super().__init__("TJBA")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
            "Content-Type": "application/json",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first-instance case consultation not implemented for TJBA."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJBA.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second-instance case consultation not implemented for TJBA."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJBA.")

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        numero_recurso: Optional[str] = None,
        orgaos: Optional[list] = None,
        relatores: Optional[list] = None,
        classes: Optional[list] = None,
        data_publicacao_inicio: Optional[str] = None,
        data_publicacao_fim: Optional[str] = None,
        segundo_grau: bool = True,
        turmas_recursais: bool = True,
        tipo_acordaos: bool = True,
        tipo_decisoes_monocraticas: bool = True,
        ordenado_por: str = "dataPublicacao",
        items_per_page: int = 10,
        session: Optional[requests.Session] = None,
        **kwargs,
    ) -> list:
        """
        Download raw results from the TJBA jurisprudence search.

        Parameters
        ----------
        pesquisa : str
            Search term. ``query`` and ``termo`` are accepted as deprecated aliases.
        paginas : int, list, range, or None
            Pages to download (1-based). int: paginas=3 downloads pages 1-3.
            range: range(1, 4) downloads pages 1-3. None: downloads all.
        numero_recurso : str, optional
            Case/appeal number filter.
        orgaos : list, optional
            List of orgao julgador IDs to filter.
        relatores : list, optional
            List of relator IDs to filter.
        classes : list, optional
            List of class IDs to filter.
        data_publicacao_inicio : str, optional
            Start date for publication filter (YYYY-MM-DD).
        data_publicacao_fim : str, optional
            End date for publication filter (YYYY-MM-DD).
        segundo_grau : bool
            Include second-instance results (default True).
        turmas_recursais : bool
            Include turmas recursais results (default True).
        tipo_acordaos : bool
            Include acordaos (default True).
        tipo_decisoes_monocraticas : bool
            Include monocratic decisions (default True).
        items_per_page : int
            Results per page (default 10).

        Returns
        -------
        list
            List of raw GraphQL response dicts (one per page).
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJBA,
            "TJBAScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            numero_recurso=numero_recurso,
            orgaos=orgaos,
            relatores=relatores,
            classes=classes,
            segundo_grau=segundo_grau,
            turmas_recursais=turmas_recursais,
            tipo_acordaos=tipo_acordaos,
            tipo_decisoes_monocraticas=tipo_decisoes_monocraticas,
            ordenado_por=ordenado_por,
            items_per_page=items_per_page,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            numero_recurso=inp.numero_recurso,
            orgaos=inp.orgaos,
            relatores=inp.relatores,
            classes=inp.classes,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
            segundo_grau=inp.segundo_grau,
            turmas_recursais=inp.turmas_recursais,
            tipo_acordaos=inp.tipo_acordaos,
            tipo_decisoes_monocraticas=inp.tipo_decisoes_monocraticas,
            ordenado_por=inp.ordenado_por,
            items_per_page=inp.items_per_page,
            session=session or self.session,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """
        Parse raw results from TJBA into a DataFrame.

        Parameters
        ----------
        resultados_brutos : list
            Raw response dicts as returned by ``cjsg_download``.

        Returns
        -------
        pd.DataFrame
            DataFrame with one row per decision.
        """
        return cjsg_parse(resultados_brutos)

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        numero_recurso: Optional[str] = None,
        orgaos: Optional[list] = None,
        relatores: Optional[list] = None,
        classes: Optional[list] = None,
        data_publicacao_inicio: Optional[str] = None,
        data_publicacao_fim: Optional[str] = None,
        segundo_grau: bool = True,
        turmas_recursais: bool = True,
        tipo_acordaos: bool = True,
        tipo_decisoes_monocraticas: bool = True,
        ordenado_por: str = "dataPublicacao",
        items_per_page: int = 10,
        session: Optional[requests.Session] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Search TJBA jurisprudence (download + parse).

        Returns a ready-to-analyze DataFrame.

        Parameters
        ----------
        pesquisa : str
            Search term. ``query`` and ``termo`` are accepted as deprecated aliases.
        paginas : int, list, range, or None
            Pages to download (1-based). None = all pages.
        data_publicacao_inicio : str, optional
            Start date (YYYY-MM-DD).
        data_publicacao_fim : str, optional
            End date (YYYY-MM-DD).

        Returns
        -------
        pd.DataFrame
            Jurisprudence results.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            numero_recurso=numero_recurso,
            orgaos=orgaos,
            relatores=relatores,
            classes=classes,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            segundo_grau=segundo_grau,
            turmas_recursais=turmas_recursais,
            tipo_acordaos=tipo_acordaos,
            tipo_decisoes_monocraticas=tipo_decisoes_monocraticas,
            ordenado_por=ordenado_por,
            items_per_page=items_per_page,
            session=session,
            **kwargs,
        )
        return self.cjsg_parse(brutos)
