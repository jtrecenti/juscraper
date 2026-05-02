"""
Scraper for the Tribunal de Justica do Estado do Para (TJPA).
"""

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, to_iso_date

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJPA


class TJPAScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Estado do Para."""

    BASE_URL = "https://jurisprudencia.tjpa.jus.br/bff/api/decisoes/buscar"

    def __init__(self):
        super().__init__("TJPA")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJPA."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJPA.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJPA."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJPA.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        relator: str | None = None,
        orgao_julgador_colegiado: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        origem: list | None = None,
        tipo: list | None = None,
        sort_by: str = "datajulgamento",
        sort_order: str = "desc",
        query_type: str = "free",
        query_scope: str = "ementa",
        **kwargs,
    ) -> list:
        """Baixa resultados crus da busca de jurisprudencia do TJPA (varias paginas).

        Filtros de data (``data_julgamento_inicio``/``_fim``,
        ``data_publicacao_inicio``/``_fim``) chegam via ``**kwargs`` e sao
        validados pelo schema :class:`InputCJSGTJPA`. Aliases deprecados
        (``data_inicio``/``data_fim``, ``query``/``termo``) sao popados antes
        da validacao.

        Returns:
            list: Respostas JSON cruas (uma por pagina).

        See also:
            :class:`InputCJSGTJPA` — fonte da verdade dos filtros aceitos.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJPA,
            "TJPAScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            relator=relator,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            assunto=assunto,
            origem=origem,
            tipo=tipo,
            sort_by=sort_by,
            sort_order=sort_order,
            query_type=query_type,
            query_scope=query_scope,
        )

        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            session=self.session,
            relator=inp.relator,
            orgao_julgador_colegiado=inp.orgao_julgador_colegiado,
            classe=inp.classe,
            assunto=inp.assunto,
            origem=inp.origem,
            tipo=inp.tipo,
            data_julgamento_inicio=to_iso_date(inp.data_julgamento_inicio),
            data_julgamento_fim=to_iso_date(inp.data_julgamento_fim),
            data_publicacao_inicio=to_iso_date(inp.data_publicacao_inicio),
            data_publicacao_fim=to_iso_date(inp.data_publicacao_fim),
            sort_by=inp.sort_by,
            sort_order=inp.sort_order,
            query_type=inp.query_type,
            query_scope=inp.query_scope,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """
        Extracts relevant data from the raw results returned by TJPA.
        Returns a DataFrame with the decisions.
        """
        return cjsg_parse_manager(resultados_brutos)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        relator: str | None = None,
        orgao_julgador_colegiado: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        origem: list | None = None,
        tipo: list | None = None,
        sort_by: str = "datajulgamento",
        sort_order: str = "desc",
        query_type: str = "free",
        query_scope: str = "ementa",
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJPA (download + parse).

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            relator (str | None): Nome do relator.
            orgao_julgador_colegiado (str | None): Orgao colegiado.
            classe (str | None): Classe processual.
            assunto (str | None): Assunto.
            origem (list | None): Lista de origens (default backend:
                ``["tribunal de justica do estado do para"]``).
            tipo (list | None): Lista de tipos de decisao (default backend:
                ``["acordao", "decisao monocratica"]``).
            sort_by (str): Campo de ordenacao. Default ``"datajulgamento"``.
            sort_order (str): ``"asc"`` ou ``"desc"``. Default ``"desc"``.
            query_type (str): ``"free"`` ou ``"any"``. Default ``"free"``.
            query_scope (str): ``"ementa"`` ou ``"inteiroteor"``. Default ``"ementa"``.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJPA`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``YYYY-MM-DD``.
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
            :class:`InputCJSGTJPA` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            relator=relator,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            assunto=assunto,
            origem=origem,
            tipo=tipo,
            sort_by=sort_by,
            sort_order=sort_order,
            query_type=query_type,
            query_scope=query_scope,
            **kwargs,
        ))
