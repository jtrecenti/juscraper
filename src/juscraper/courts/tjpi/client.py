"""Scraper for the Tribunal de Justica do Piaui (TJPI)."""

from typing import Any

import pandas as pd

from juscraper.core.http import HTTPScraper
from juscraper.utils.params import apply_input_pipeline_search, to_iso_date

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJPI


class TJPIScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica do Piaui (TJPI).

    Uses the JusPI search interface at jurisprudencia.tjpi.jus.br.
    Results are HTML-based (server-rendered) and parsed with BeautifulSoup.
    """

    BASE_URL = "https://jurisprudencia.tjpi.jus.br"

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__(
            "TJPI",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJPI."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJPI.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJPI."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJPI.")

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo: str | None = None,
        relator: str | None = None,
        classe: str | None = None,
        orgao: str | None = None,
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
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo: str | None = None,
        relator: str | None = None,
        classe: str | None = None,
        orgao: str | None = None,
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
            request_fn=self._request_with_retry,
            sleep_time=self.sleep_time,
            tipo=inp.tipo or "",
            relator=inp.relator or "",
            classe=inp.classe or "",
            orgao=inp.orgao or "",
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
