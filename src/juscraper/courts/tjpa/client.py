"""
Scraper for the Tribunal de Justica do Estado do Para (TJPA).
"""
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.schemas import BuscarEm
from juscraper.utils.deprecacao import resolve_buscar_em
from juscraper.utils.params import apply_input_pipeline_search, to_iso_date

from .download import QUERY_SCOPE, cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJPA, QueryType, SortBy

#: Valores do alias deprecado ``query_scope`` -> ``buscar_em``; ``"inteiroteor"`` e a grafia da docstring antiga.
_QUERY_SCOPE_PARA_BUSCAR_EM = {scope: buscar_em for buscar_em, scope in QUERY_SCOPE.items()} | {
    "inteiroteor": "inteiro_teor",
}
#: ``buscar_em`` mais os valores de ``query_scope`` (convertidos, com aviso) e ``None`` (default do schema).
BuscarEmAceito = BuscarEm | Literal["inteiroTeor", "inteiroteor"] | None


class TJPAScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica do Estado do Para."""

    BASE_URL = "https://jurisprudencia.tjpa.jus.br/bff/api/decisoes/buscar"

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=30),
    }

    def __init__(self, *, politica: Mapping[str, Mapping[str, Any]] | None = None):
        super().__init__("TJPA", politica=politica)

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
        sort_by: SortBy = "datajulgamento",
        sort_order: Literal["asc", "desc"] = "desc",
        query_type: QueryType = "free",
        buscar_em: BuscarEmAceito = None,
        **kwargs,
    ) -> list:
        """Baixa resultados crus da busca de jurisprudencia do TJPA (varias paginas).

        Aceita os mesmos parâmetros e aliases deprecados de :meth:`cjsg`; veja lá
        a lista completa.

        Returns:
            Respostas JSON cruas (uma por pagina).

        See also:
            :class:`InputCJSGTJPA` — fonte da verdade dos filtros aceitos.
        """
        resolve_buscar_em(kwargs, "query_scope", buscar_em, _QUERY_SCOPE_PARA_BUSCAR_EM)
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
        )

        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            request_fn=self._request_with_retry,
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
            buscar_em=inp.buscar_em,
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
        sort_by: SortBy = "datajulgamento",
        sort_order: Literal["asc", "desc"] = "desc",
        query_type: QueryType = "free",
        buscar_em: BuscarEmAceito = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJPA (download + parse).

        Args:
            pesquisa: Termo de busca livre, procurado no campo indicado
                por ``buscar_em``.
            paginas: Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            relator: Nome do relator.
            orgao_julgador_colegiado: Orgao colegiado.
            classe: Classe processual.
            assunto: Assunto.
            origem: Lista de origens (default backend:
                ``["tribunal de justica do estado do para"]``).
            tipo: Lista de tipos de decisao (default backend:
                ``["acordao", "decisao monocratica"]``).
            sort_by: ``"datajulgamento"`` (default), ``"datapublicacao"``
                ou ``"relevancia"``. O indice do portal tem decisoes com data
                de julgamento impossivel, como o ano 8201 ou 2106 (observado
                em 15/11/2026), e, com o default (``"datajulgamento"`` em
                ordem ``"desc"``), elas vem primeiro. O juscraper repassa a
                data como a fonte a entrega; para exclui-las, filtre
                ``data_julgamento_fim``. Outra ordenacao so as tira do topo.
            sort_order: ``"asc"`` ou ``"desc"``. Default ``"desc"``.
            query_type: ``"free"`` (default) ou ``"anywords"``.
            buscar_em: Onde procurar ``pesquisa``: ``"ementa"``
                (default; ``None`` tambem) ou ``"inteiro_teor"`` (texto
                integral da decisao, que inclui a ementa), as duas opcoes do
                portal. Outro valor levanta ``ValidationError``. Em
                26/11/2026, a API ignorava a escolha, tambem no site: as duas
                procuravam o termo na ementa e no inteiro teor e traziam o
                mesmo resultado.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJPA`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str | date | None): nos mesmos formatos.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``
            * ``query_scope`` -> ``buscar_em``: ``"ementa"`` continua
              ``"ementa"``; ``"inteiroTeor"`` e ``"inteiroteor"`` viram
              ``"inteiro_teor"``, tambem quando passados em ``buscar_em``
              (``query_scope`` por posicao), com aviso

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.
            ValueError: Quando ``query_scope`` e ``buscar_em`` sao passados juntos.

        Returns:
            DataFrame com as decisoes. ``ementa`` e ``None`` na decisao
                monocratica, que o portal manda sem ementa.

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
            buscar_em=buscar_em,
            **kwargs,
        ))
