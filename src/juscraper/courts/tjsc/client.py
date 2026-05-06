"""Scraper for the Tribunal de Justica de Santa Catarina (TJSC)."""
from typing import Literal

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJSC


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

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJSC."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJSC.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJSC."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJSC.")

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        campo: Literal["E", "I"] = "E",
        processo: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJSC.

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            campo (str): Campo de busca: ``"E"`` para ementa (default),
                ``"I"`` para inteiro teor.
            processo (str): Filtro por numero do processo.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJSC`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``YYYY-MM-DD``. Mapeado para ``dt_decisao_*`` no backend.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim`` (str):
                  ``YYYY-MM-DD``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: DataFrame com as decisoes.

        See also:
            :class:`InputCJSGTJSC` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            campo=campo,
            processo=processo,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        campo: Literal["E", "I"] = "E",
        processo: str | None = None,
        **kwargs,
    ) -> list:
        """Download raw HTML pages from TJSC.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns
        -------
        list
            List of raw HTML strings (one per page).
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJSC,
            "TJSCScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            campo=campo,
            processo=processo,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            session=self.session,
            campo=inp.campo,
            processo=inp.processo or "",
            dt_decisao_inicio=inp.data_julgamento_inicio or "",
            dt_decisao_fim=inp.data_julgamento_fim or "",
            dt_publicacao_inicio=inp.data_publicacao_inicio or "",
            dt_publicacao_fim=inp.data_publicacao_fim or "",
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded HTML pages.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
