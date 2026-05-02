"""Scraper for the Tribunal de Justica do Piaui (TJPI)."""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, to_iso_date

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJPI


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
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo: str = "",
        relator: str = "",
        classe: str = "",
        orgao: str = "",
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJPI.

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            tipo (str): Tipo de decisao. Opcoes: ``"Acordao"``,
                ``"Decisao Terminativa"``, ``"Sumula"``.
            relator (str): Nome do relator (deve bater com o valor do dropdown).
            classe (str): Classe processual (deve bater com o valor do dropdown).
            orgao (str): Orgao julgador (deve bater com o valor do dropdown).
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJPI`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``YYYY-MM-DD``. Mapeado para ``data_min``/``data_max`` no
                  GET (refs #94).

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado (inclusive
                ``data_publicacao_*``, que o backend nao expoe).
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: DataFrame com as decisoes.

        See also:
            :class:`InputCJSGTJPI` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            tipo=tipo,
            relator=relator,
            classe=classe,
            orgao=orgao,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo: str = "",
        relator: str = "",
        classe: str = "",
        orgao: str = "",
        **kwargs,
    ) -> list:
        """Download raw HTML pages from TJPI.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns
        -------
        list
            List of raw HTML strings (one per page).
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJPI,
            "TJPIScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            tipo=tipo,
            relator=relator,
            classe=classe,
            orgao=orgao,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            session=self.session,
            tipo=inp.tipo,
            relator=inp.relator,
            classe=inp.classe,
            orgao=inp.orgao,
            data_min=to_iso_date(inp.data_julgamento_inicio) or "",
            data_max=to_iso_date(inp.data_julgamento_fim) or "",
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded HTML pages.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
