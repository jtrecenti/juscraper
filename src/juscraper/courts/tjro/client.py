"""Scraper for the Tribunal de Justica de Rondonia (TJRO)."""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias, to_iso_date

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJRO


class TJROScraper(BaseScraper):
    """Scraper for the Tribunal de Justica de Rondonia (TJRO).

    Uses the JURIS Elasticsearch backend at juris-back.tjro.jus.br.
    """

    BASE_URL = "https://juris.tjro.jus.br"

    def __init__(self):
        super().__init__("TJRO")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJRO."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJRO.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJRO."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJRO.")

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo: list | None = None,
        numero_processo: Optional[str] = None,
        relator: Optional[str] = None,
        orgao_julgador: int | str | None = None,
        orgao_julgador_colegiado: int | str | None = None,
        classe: Optional[str] = None,
        instancia: list | None = None,
        termo_exato: bool = False,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJRO.

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            tipo (list | None): Tipos de documento. Default backend
                ``["EMENTA"]``. Opcoes incluem ``"ACORDAO"``, ``"DECISAO"``,
                ``"SENTENCA"``, ``"VOTO"``, etc.
            numero_processo (str): Numero CNJ. Aceita o alias deprecado
                ``nr_processo``.
            relator (str): Nome do relator. Aceita o alias deprecado
                ``magistrado`` (refs #129).
            orgao_julgador (int | str): ID do orgao julgador.
            orgao_julgador_colegiado (int | str): ID do orgao colegiado.
            classe (str): Nome da classe judicial. Aceita o alias deprecado
                ``classe_judicial`` (refs #129).
            instancia (list | None): Instancias (ex.: ``[1]``, ``[2]``, ``[1, 2]``).
            termo_exato (bool): Busca por termo exato.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJRO`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``YYYY-MM-DD``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``nr_processo`` -> ``numero_processo``
            * ``magistrado`` -> ``relator``
            * ``classe_judicial`` -> ``classe``
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
            :class:`InputCJSGTJRO` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            tipo=tipo,
            numero_processo=numero_processo,
            relator=relator,
            orgao_julgador=orgao_julgador,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            instancia=instancia,
            termo_exato=termo_exato,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo: list | None = None,
        numero_processo: Optional[str] = None,
        relator: Optional[str] = None,
        orgao_julgador: int | str | None = None,
        orgao_julgador_colegiado: int | str | None = None,
        classe: Optional[str] = None,
        instancia: list | None = None,
        termo_exato: bool = False,
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJRO.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns
        -------
        list
            List of raw JSON responses (one per page).
        """
        numero_processo = resolve_deprecated_alias(
            kwargs, "nr_processo", "numero_processo", numero_processo
        )
        relator = resolve_deprecated_alias(
            kwargs, "magistrado", "relator", relator
        )
        classe = resolve_deprecated_alias(
            kwargs, "classe_judicial", "classe", classe
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJRO,
            "TJROScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            tipo=tipo,
            numero_processo=numero_processo,
            relator=relator,
            orgao_julgador=orgao_julgador,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            instancia=instancia,
            termo_exato=termo_exato,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            session=self.session,
            tipo=inp.tipo,
            nr_processo=inp.numero_processo or "",
            relator=inp.relator or "",
            orgao_julgador=inp.orgao_julgador if inp.orgao_julgador is not None else "",
            orgao_julgador_colegiado=(
                inp.orgao_julgador_colegiado if inp.orgao_julgador_colegiado is not None else ""
            ),
            classe=inp.classe or "",
            data_julgamento_inicio=to_iso_date(inp.data_julgamento_inicio) or "",
            data_julgamento_fim=to_iso_date(inp.data_julgamento_fim) or "",
            instancia=inp.instancia,
            termo_exato=inp.termo_exato,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded CJSG JSON responses.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
