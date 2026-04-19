"""
Scraper for the Tribunal de Justica do Estado do Para (TJPA).
"""
from typing import Union, List

import pandas as pd
import requests
from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_paginas, normalize_pesquisa, normalize_datas, to_iso_date
from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


class TJPAScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Estado do Para."""

    BASE_URL = "https://jurisprudencia.tjpa.jus.br/bff/api/decisoes/buscar"

    def __init__(self):
        super().__init__("TJPA")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJPA."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJPA.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJPA."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJPA.")

    def cjsg_download(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        relator: str = None,
        orgao_julgador_colegiado: str = None,
        classe: str = None,
        assunto: str = None,
        origem: list = None,
        tipo: list = None,
        data_julgamento_inicio: str = None,
        data_julgamento_fim: str = None,
        data_publicacao_inicio: str = None,
        data_publicacao_fim: str = None,
        sort_by: str = "datajulgamento",
        sort_order: str = "desc",
        query_type: str = "free",
        query_scope: str = "ementa",
        **kwargs,
    ) -> list:
        """
        Downloads raw results from the TJPA jurisprudence search (multiple pages).
        Returns a list of raw JSON responses.

        Args:
            pesquisa: Search term. ``query`` and ``termo`` are accepted as deprecated aliases.
            paginas (int, list, range, or None): Pages to download (1-based).
                int: paginas=3 downloads pages 1-3.
                range: range(1, 4) downloads pages 1-3.
                None: downloads all available pages.
            relator: Filter by relator name.
            orgao_julgador_colegiado: Filter by collegiate judging body.
            classe: Filter by procedural class.
            assunto: Filter by subject.
            origem: List of origins (default: ["tribunal de justica do estado do para"]).
            tipo: List of decision types (default: ["acordao", "decisao monocratica"]).
            data_julgamento_inicio: Start date for judgment filter (YYYY-MM-DD).
            data_julgamento_fim: End date for judgment filter (YYYY-MM-DD).
            data_publicacao_inicio: Start date for publication filter (YYYY-MM-DD).
            data_publicacao_fim: End date for publication filter (YYYY-MM-DD).
            sort_by: Sort field (default: "datajulgamento").
            sort_order: Sort order, "asc" or "desc" (default: "desc").
            query_type: Query type, "free" or "any" (default: "free").
            query_scope: Query scope, "ementa" or "inteiroteor" (default: "ementa").
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        return cjsg_download_manager(
            pesquisa=pesquisa,
            paginas=paginas,
            session=self.session,
            relator=relator,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            assunto=assunto,
            origem=origem,
            tipo=tipo,
            data_julgamento_inicio=to_iso_date(datas["data_julgamento_inicio"]),
            data_julgamento_fim=to_iso_date(datas["data_julgamento_fim"]),
            data_publicacao_inicio=to_iso_date(datas["data_publicacao_inicio"]),
            data_publicacao_fim=to_iso_date(datas["data_publicacao_fim"]),
            sort_by=sort_by,
            sort_order=sort_order,
            query_type=query_type,
            query_scope=query_scope,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """
        Extracts relevant data from the raw results returned by TJPA.
        Returns a DataFrame with the decisions.
        """
        return cjsg_parse_manager(resultados_brutos)

    def cjsg(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        relator: str = None,
        orgao_julgador_colegiado: str = None,
        classe: str = None,
        assunto: str = None,
        origem: list = None,
        tipo: list = None,
        data_julgamento_inicio: str = None,
        data_julgamento_fim: str = None,
        data_publicacao_inicio: str = None,
        data_publicacao_fim: str = None,
        sort_by: str = "datajulgamento",
        sort_order: str = "desc",
        query_type: str = "free",
        query_scope: str = "ementa",
        **kwargs,
    ) -> pd.DataFrame:
        """
        Fetches jurisprudence from TJPA in a simplified way (download + parse).
        Returns a ready-to-analyze DataFrame.

        Args:
            pesquisa: Search term.
            paginas (int, list, range, or None): Pages to download (1-based).
            relator: Filter by relator name.
            orgao_julgador_colegiado: Filter by collegiate judging body.
            classe: Filter by procedural class.
            assunto: Filter by subject.
            origem: List of origins.
            tipo: List of decision types.
            data_julgamento_inicio: Start date for judgment filter (YYYY-MM-DD).
            data_julgamento_fim: End date for judgment filter (YYYY-MM-DD).
            data_publicacao_inicio: Start date for publication filter (YYYY-MM-DD).
            data_publicacao_fim: End date for publication filter (YYYY-MM-DD).
            sort_by: Sort field (default: "datajulgamento").
            sort_order: Sort order (default: "desc").
            query_type: Query type (default: "free").
            query_scope: Query scope (default: "ementa").
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            relator=relator,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            assunto=assunto,
            origem=origem,
            tipo=tipo,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            sort_by=sort_by,
            sort_order=sort_order,
            query_type=query_type,
            query_scope=query_scope,
            **kwargs,
        )
        return self.cjsg_parse(brutos)
