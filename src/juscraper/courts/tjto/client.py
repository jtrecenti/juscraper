"""
Scraper for the Tribunal de Justica do Tocantins (TJTO).
"""
import logging
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search

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
        inp,
        instancia: str,
        session: Optional["requests.Session"] = None,
    ) -> list:
        """Shared download logic for cjsg and cjpg.

        Receives a validated pydantic instance and dispatches to the
        download manager. ``instancia`` is the only field that varies
        between cjsg (``"2"``) and cjpg (``"1"``); it does not live in
        the schema because it is set by the calling method, not the user.
        """
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

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns:
            list: Lista de paginas HTML cruas.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJTO,
            "TJTOScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            tipo_documento=tipo_documento,
            ordenacao=ordenacao,
            numero_processo=numero_processo,
            soementa=soementa,
        )
        return self._download_internal(inp, instancia="2", session=session)

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
        """Busca jurisprudencia de 2o grau no TJTO (download + parse).

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            tipo_documento (str): ``"acordaos"`` (default), ``"decisoes"`` ou
                ``"sentencas"``.
            ordenacao (str): ``"DESC"`` (mais recentes, default), ``"ASC"``
                (mais antigos), ``"RELEV"`` (mais relevantes).
            numero_processo (str): Filtro por numero CNJ do processo.
            data_julgamento_inicio (str | date | datetime | None): Data inicial.
                Aceita ``DD/MM/YYYY``, ``DD-MM-YYYY``, ``YYYY-MM-DD``,
                ``YYYY/MM/DD``, ``date`` ou ``datetime``.
            data_julgamento_fim (str | date | datetime | None): Data final
                (mesmos formatos).
            soementa (bool): Se ``True``, restringe busca ao texto da ementa.
            session (requests.Session | None): Sessao opcional para reuso.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJTO`.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando um canonico e seu alias deprecado sao passados
                simultaneamente.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: DataFrame com as decisoes.

        See also:
            :class:`InputCJSGTJTO` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
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
        Aceita os mesmos filtros de :meth:`cjpg`; veja la a lista completa.

        Returns:
            list: Lista de paginas HTML cruas.
        """
        inp = apply_input_pipeline_search(
            InputCJPGTJTO,
            "TJTOScraper.cjpg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            tipo_documento=tipo_documento,
            ordenacao=ordenacao,
            numero_processo=numero_processo,
            soementa=soementa,
        )
        return self._download_internal(inp, instancia="1", session=session)

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
        """Busca jurisprudencia de 1o grau no TJTO (download + parse).

        Mesmos parametros de :meth:`cjsg` — a unica diferenca interna e
        ``instancia='1'`` em vez de ``'2'``. Veja a docstring de :meth:`cjsg`
        para a lista completa.

        See also:
            :class:`InputCJPGTJTO` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
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
