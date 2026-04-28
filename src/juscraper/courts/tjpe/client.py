"""
Scraper for the Tribunal de Justica de Pernambuco (TJPE).
"""

from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_datas, normalize_paginas, normalize_pesquisa, resolve_deprecated_alias

from .download import cjsg_download
from .parse import cjsg_parse


class TJPEScraper(BaseScraper):
    """Scraper for the Tribunal de Justica de Pernambuco."""

    BASE_URL = "https://www.tjpe.jus.br/consultajurisprudenciaweb"

    def __init__(self):
        super().__init__("TJPE")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJPE."""
        raise NotImplementedError("Consulta de processos de 1 grau não implementada para TJPE.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJPE."""
        raise NotImplementedError("Consulta de processos de 2 grau não implementada para TJPE.")

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        relator: Optional[str] = None,
        classe: Optional[str] = None,
        assunto: Optional[str] = None,
        meio_tramitacao: Optional[str] = None,
        tipo_decisao: str = "acordaos",
        session: Optional[requests.Session] = None,
        **kwargs,
    ) -> list:
        """
        Download raw HTML pages from the TJPE jurisprudence search.

        Args:
            pesquisa: Search term.
            paginas: Pages to download (1-based). int, list, range, or None (all).
            data_julgamento_inicio: Start date for judgment filter (DD/MM/YYYY).
            data_julgamento_fim: End date for judgment filter (DD/MM/YYYY).
            relator: Relator name (must match dropdown value exactly).
            classe: CNJ class code. Accepts the deprecated alias ``classe_cnj``.
            assunto: CNJ subject code. Accepts the deprecated alias ``assunto_cnj``.
            meio_tramitacao: Tramitation medium filter.
            tipo_decisao: 'acordaos', 'monocraticas', or 'todos'.

        Returns:
            List of raw HTML strings, one per page.
        """
        classe = resolve_deprecated_alias(kwargs, "classe_cnj", "classe", classe)
        assunto = resolve_deprecated_alias(kwargs, "assunto_cnj", "assunto", assunto)
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            **kwargs,
        )
        if session is None:
            session = self.session
        return cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            data_julgamento_inicio=datas["data_julgamento_inicio"],
            data_julgamento_fim=datas["data_julgamento_fim"],
            relator=relator,
            classe_cnj=classe,
            assunto_cnj=assunto,
            meio_tramitacao=meio_tramitacao,
            tipo_decisao=tipo_decisao,
            session=session,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """
        Parse raw HTML pages from cjsg_download into a DataFrame.
        """
        return cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        relator: Optional[str] = None,
        classe: Optional[str] = None,
        assunto: Optional[str] = None,
        meio_tramitacao: Optional[str] = None,
        tipo_decisao: str = "acordaos",
        session: Optional[requests.Session] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Search TJPE jurisprudence (download + parse).

        Args:
            pesquisa: Search term.
            paginas: Pages to download (1-based). int, list, range, or None (all).
            data_julgamento_inicio: Start date (DD/MM/YYYY).
            data_julgamento_fim: End date (DD/MM/YYYY).
            relator: Relator name.
            classe: CNJ class code. Accepts the deprecated alias ``classe_cnj``.
            assunto: CNJ subject code. Accepts the deprecated alias ``assunto_cnj``.
            meio_tramitacao: Tramitation medium.
            tipo_decisao: 'acordaos', 'monocraticas', or 'todos'.

        Returns:
            DataFrame with jurisprudence results.
        """
        raw = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            relator=relator,
            classe=classe,
            assunto=assunto,
            meio_tramitacao=meio_tramitacao,
            tipo_decisao=tipo_decisao,
            session=session,
            **kwargs,
        )
        return self.cjsg_parse(raw)
