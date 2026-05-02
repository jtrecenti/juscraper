"""Scraper for the Tribunal de Justica de Roraima (TJRR)."""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJRR


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
        """Busca jurisprudencia no TJRR.

        Args:
            pesquisa (str): Termo de busca livre (busca na ementa).
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            relator (str): Nome do relator. **Aceito por compat de API**, mas
                hoje o backend nao expoe campo de texto livre para relator
                (virou multi-select de IDs); o filtro e descartado pelo
                Projudi/PrimeFaces. Refs #158 (deprecation/remocao planejada).
            orgao_julgador (list[str] | None): Codigos do orgao julgador
                (ex.: ``["PRIMEIRA_TURMA_CIVEL"]``). Backend:
                ``menuinicial:tipoOrgaoList``.
            especie (list[str] | None): Codigos do tipo de decisao
                (ex.: ``["ACORDAO"]``). Backend: ``menuinicial:tipoEspecieList``.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJRR`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``DD/MM/AAAA``. Backend: ``menuinicial:datainicial_input``
                  / ``menuinicial:datafinal_input``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: DataFrame com as decisoes.

        See also:
            :class:`InputCJSGTJRR` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            relator=relator,
            orgao_julgador=orgao_julgador,
            especie=especie,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        relator: str = "",
        orgao_julgador: list | None = None,
        especie: list | None = None,
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        **kwargs,
    ) -> list:
        """Download raw HTML pages from TJRR.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns
        -------
        list
            List of raw HTML strings (one per page).
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJRR,
            "TJRRScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            relator=relator,
            orgao_julgador=orgao_julgador,
            especie=especie,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            session=self.session,
            relator=inp.relator,
            data_inicio=inp.data_julgamento_inicio or "",
            data_fim=inp.data_julgamento_fim or "",
            orgao_julgador=inp.orgao_julgador,
            especie=inp.especie,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded HTML pages.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
