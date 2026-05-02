"""Scraper for the Tribunal de Justica do Rio Grande do Norte (TJRN)."""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias, to_br_date

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJRN


def _to_tjrn_date(date_str):
    """Convert BR or ISO dates to TJRN's DD-MM-YYYY format.

    The UI at jurisprudencia.tjrn.jus.br sends ``dt_inicio``/``dt_fim`` as
    ``DD-MM-YYYY`` (dashes, not slashes); slashes are silently ignored and
    the backend returns unfiltered results.
    """
    if not date_str:
        return ""
    br = to_br_date(date_str)
    return br.replace("/", "-") if br else ""


class TJRNScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Rio Grande do Norte (TJRN).

    Uses the TJRN Elasticsearch-based JSON API at jurisprudencia.tjrn.jus.br.
    """

    BASE_URL = "https://jurisprudencia.tjrn.jus.br"

    def __init__(self):
        super().__init__("TJRN")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJRN."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJRN.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJRN."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJRN.")

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        numero_processo: str = "",
        id_classe_judicial: str = "",
        id_orgao_julgador: str = "",
        id_relator: str = "",
        id_colegiado: str = "",
        sistema: str = "",
        decisoes: str = "",
        jurisdicoes: str = "",
        grau: str = "",
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJRN.

        Args:
            pesquisa (str): Termo de busca livre (busca na ementa).
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            numero_processo (str): Numero CNJ do processo. Aceita o alias
                deprecado ``nr_processo``.
            id_classe_judicial (str): ID da classe judicial.
            id_orgao_julgador (str): ID do orgao julgador.
            id_relator (str): ID do relator.
            id_colegiado (str): ID do colegiado.
            sistema (str): ``"PJE"``, ``"SAJ"`` ou vazio para todos.
            decisoes (str): ``"Monocraticas"``, ``"Colegiadas"``,
                ``"Sentencas"`` ou vazio para todos.
            jurisdicoes (str): ``"Tribunal de Justica"``, ``"Turmas Recursais"``
                ou vazio para todos.
            grau (str): ``"1"`` (primeiro), ``"2"`` (segundo) ou vazio para todos.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJRN`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``YYYY-MM-DD``. Convertido para ``DD-MM-YYYY`` antes do
                  envio ao backend.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``nr_processo`` -> ``numero_processo``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando ``numero_processo`` e ``nr_processo`` sao
                passados simultaneamente.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: DataFrame com as decisoes.

        See also:
            :class:`InputCJSGTJRN` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            numero_processo=numero_processo,
            id_classe_judicial=id_classe_judicial,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_colegiado=id_colegiado,
            sistema=sistema,
            decisoes=decisoes,
            jurisdicoes=jurisdicoes,
            grau=grau,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        numero_processo: str = "",
        id_classe_judicial: str = "",
        id_orgao_julgador: str = "",
        id_relator: str = "",
        id_colegiado: str = "",
        sistema: str = "",
        decisoes: str = "",
        jurisdicoes: str = "",
        grau: str = "",
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJRN.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns
        -------
        list
            List of raw JSON responses (one per page).
        """
        numero_processo = resolve_deprecated_alias(
            kwargs, "nr_processo", "numero_processo", numero_processo, sentinel=""
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJRN,
            "TJRNScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            numero_processo=numero_processo,
            id_classe_judicial=id_classe_judicial,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_colegiado=id_colegiado,
            sistema=sistema,
            decisoes=decisoes,
            jurisdicoes=jurisdicoes,
            grau=grau,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            session=self.session,
            nr_processo=inp.numero_processo,
            id_classe_judicial=inp.id_classe_judicial,
            id_orgao_julgador=inp.id_orgao_julgador,
            id_relator=inp.id_relator,
            id_colegiado=inp.id_colegiado,
            dt_inicio=_to_tjrn_date(inp.data_julgamento_inicio),
            dt_fim=_to_tjrn_date(inp.data_julgamento_fim),
            sistema=inp.sistema,
            decisoes=inp.decisoes,
            jurisdicoes=inp.jurisdicoes,
            grau=inp.grau,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded CJSG JSON responses.

        Parameters
        ----------
        resultados_brutos : list
            List of raw JSON responses from the TJRN API.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
