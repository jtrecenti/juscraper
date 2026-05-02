"""
Scraper for the Tribunal de Justica do Tocantins (TJTO).
"""
import logging
from typing import List, Optional, Union

import pandas as pd
import requests
from pydantic import BaseModel

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, normalize_paginas, normalize_pesquisa

from .download import TYPE_MINUTA_MAP, _fetch_ementa, cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJPGTJTO, InputCJSGTJTO

logger = logging.getLogger(__name__)


class TJTOScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Tocantins."""

    BASE_URL = "https://jurisprudencia.tjto.jus.br/consulta.php"

    def __init__(self):
        super().__init__("TJTO")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJTO."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJTO.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJTO."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJTO.")

    def _download_internal(
        self,
        pesquisa,
        paginas,
        instancia: str,
        schema_cls: type[BaseModel],
        method_name: str,
        tipo_documento: str = "acordaos",
        ordenacao: str = "DESC",
        numero_processo: str = "",
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        soementa: bool = False,
        session: Optional["requests.Session"] = None,
        **kwargs,
    ) -> list:
        """Shared download logic for cjsg and cjpg."""
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        inp = apply_input_pipeline_search(
            schema_cls,
            method_name,
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            tipo_documento=tipo_documento,
            ordenacao=ordenacao,
            numero_processo=numero_processo,
            soementa=soementa,
        )

        type_minuta = TYPE_MINUTA_MAP.get(inp.tipo_documento, "1")

        if session is None:
            session = self.session

        return cjsg_download_manager(
            termo=inp.pesquisa,
            paginas=inp.paginas,
            type_minuta=type_minuta,
            tip_criterio_inst=instancia,
            tip_criterio_data=inp.ordenacao,
            numero_processo=inp.numero_processo,
            dat_jul_ini=inp.data_julgamento_inicio or "",
            dat_jul_fim=inp.data_julgamento_fim or "",
            soementa=inp.soementa,
            session=session,
        )

    # --- cjsg (2o grau) ---

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo_documento: str = "acordaos",
        ordenacao: str = "DESC",
        numero_processo: str = "",
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        soementa: bool = False,
        session: Optional["requests.Session"] = None,
        **kwargs,
    ) -> list:
        """Download raw HTML pages from the TJTO second-instance jurisprudence search.

        Args:
            pesquisa: Search term.
            paginas: Pages to download (1-based). int, list, range, or None (all).
            tipo_documento: 'acordaos', 'decisoes', or 'sentencas'.
            ordenacao: 'DESC' (most recent), 'ASC' (oldest), 'RELEV' (most relevant).
            numero_processo: Filter by process number.
            data_julgamento_inicio: Start date for judgment filter (DD/MM/YYYY).
            data_julgamento_fim: End date for judgment filter (DD/MM/YYYY).
            soementa: If True, restrict search to ementa text only.

        Returns:
            List of raw HTML strings.
        """
        return self._download_internal(
            pesquisa=pesquisa,
            paginas=paginas,
            instancia="2",
            schema_cls=InputCJSGTJTO,
            method_name="TJTOScraper.cjsg_download()",
            tipo_documento=tipo_documento,
            ordenacao=ordenacao,
            numero_processo=numero_processo,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            soementa=soementa,
            session=session,
            **kwargs,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse raw HTML pages downloaded by cjsg_download.

        Args:
            resultados_brutos: List of raw HTML strings.

        Returns:
            DataFrame with parsed results.
        """
        return cjsg_parse_manager(resultados_brutos)

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo_documento: str = "acordaos",
        ordenacao: str = "DESC",
        numero_processo: str = "",
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        soementa: bool = False,
        session: Optional["requests.Session"] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Fetch second-instance jurisprudence from TJTO (download + parse).

        Args:
            pesquisa: Search term.
            paginas: Pages to download (1-based). int, list, range, or None (all).
            tipo_documento: 'acordaos', 'decisoes', or 'sentencas'.
            ordenacao: 'DESC' (most recent), 'ASC' (oldest), 'RELEV' (most relevant).
            numero_processo: Filter by process number.
            data_julgamento_inicio: Start date (DD/MM/YYYY).
            data_julgamento_fim: End date (DD/MM/YYYY).
            soementa: If True, restrict search to ementa text only.

        Returns:
            DataFrame with jurisprudence results.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            tipo_documento=tipo_documento,
            ordenacao=ordenacao,
            numero_processo=numero_processo,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            soementa=soementa,
            session=session,
            **kwargs,
        )
        return self.cjsg_parse(brutos)

    # --- cjpg (1o grau) ---

    def cjpg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo_documento: str = "acordaos",
        ordenacao: str = "DESC",
        numero_processo: str = "",
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        soementa: bool = False,
        session: Optional["requests.Session"] = None,
        **kwargs,
    ) -> list:
        """Download raw HTML pages from the TJTO first-instance jurisprudence search.

        Shortcut for the download with ``instancia='1'``.
        Accepts the same parameters as :meth:`cjsg_download`.

        Returns:
            List of raw HTML strings.
        """
        return self._download_internal(
            pesquisa=pesquisa,
            paginas=paginas,
            instancia="1",
            schema_cls=InputCJPGTJTO,
            method_name="TJTOScraper.cjpg_download()",
            tipo_documento=tipo_documento,
            ordenacao=ordenacao,
            numero_processo=numero_processo,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            soementa=soementa,
            session=session,
            **kwargs,
        )

    def cjpg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse raw HTML pages downloaded by cjpg_download.

        Args:
            resultados_brutos: List of raw HTML strings.

        Returns:
            DataFrame with parsed results.
        """
        return cjsg_parse_manager(resultados_brutos)

    def cjpg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo_documento: str = "acordaos",
        ordenacao: str = "DESC",
        numero_processo: str = "",
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        soementa: bool = False,
        session: Optional["requests.Session"] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Fetch first-instance jurisprudence from TJTO (download + parse).

        Shortcut for :meth:`cjpg_download` + :meth:`cjpg_parse`.
        Queries only first-instance results (``instancia='1'``).
        Accepts the same parameters as :meth:`cjsg`.

        Returns:
            DataFrame with jurisprudence results.
        """
        brutos = self.cjpg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            tipo_documento=tipo_documento,
            ordenacao=ordenacao,
            numero_processo=numero_processo,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            soementa=soementa,
            session=session,
            **kwargs,
        )
        return self.cjpg_parse(brutos)

    # --- ementa ---

    def cjsg_ementa(self, uuid: str) -> dict:
        """Fetch the ementa for a specific document by UUID.

        Args:
            uuid: The document UUID (from the 'uuid' column in cjsg/cjpg results).

        Returns:
            Dict with ementa text and process number.
        """
        return _fetch_ementa(self.session, uuid)
