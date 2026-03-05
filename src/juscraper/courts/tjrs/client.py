"""
Scraper for the Tribunal de Justiça do Rio Grande do Sul (TJRS).
"""
from typing import Union, List
import requests
import pandas as pd
from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_paginas, normalize_pesquisa, normalize_datas
from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


class TJRSScraper(BaseScraper):
    """Scraper for the Tribunal de Justiça do Rio Grande do Sul."""

    BASE_URL = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"
    DEFAULT_PARAMS = {
        "tipo-busca": "jurisprudencia-mob",
        "client": "tjrs_index",
        "proxystylesheet": "tjrs_index",
        "lr": "lang_pt",
        "oe": "UTF-8",
        "ie": "UTF-8",
        "getfields": "*",
        "filter": "0",
        "entqr": "3",
        "content": "body",
        "accesskey": "p",
        "ulang": "",
        "entqrm": "0",
        "ud": "1",
        "start": "0",
        "aba": "jurisprudencia",
        "sort": "date:D:L:d1"
    }

    def __init__(self):
        super().__init__("TJRS")
        self.session = requests.Session()

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """
        Fetches jurisprudence from TJRS in a simplified way (download + parse).
        Returns a DataFrame ready for analysis.
        """
        print(f"[TJRS] Consulting process: {id_cnj}")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """
        Fetches jurisprudence from TJRS in a simplified way (download + parse).
        Returns a DataFrame ready for analysis.
        """
        print(f"[TJRS] Consulting process: {id_cnj}")

    def cjsg_download(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        classe: str = None,
        assunto: str = None,
        orgao_julgador: str = None,
        relator: str = None,
        data_julgamento_inicio: str = None,
        data_julgamento_fim: str = None,
        data_publicacao_inicio: str = None,
        data_publicacao_fim: str = None,
        tipo_processo: str = None,
        secao: str = None,
        session: 'requests.Session' = None,
        **kwargs,
    ) -> list:
        """
        Downloads raw results from the TJRS 'jurisprudence search' (multiple pages).
        Returns a list of raw results (JSON).

        Args:
            pesquisa: Search term. ``query`` and ``termo`` are accepted as deprecated aliases.
            paginas (int, list, range, or None): Pages to download (1-based).
                int: paginas=3 downloads pages 1-3.
                range: range(1, 4) downloads pages 1-3.
                None: downloads all available pages.
            secao: 'civel', 'crime', or None.
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
        )
        if session is None:
            session = self.session
        return cjsg_download_manager(
            termo=pesquisa,
            paginas=paginas,
            classe=classe,
            assunto=assunto,
            orgao_julgador=orgao_julgador,
            relator=relator,
            data_julgamento_inicio=datas["data_julgamento_inicio"],
            data_julgamento_fim=datas["data_julgamento_fim"],
            data_publicacao_inicio=datas["data_publicacao_inicio"],
            data_publicacao_fim=datas["data_publicacao_fim"],
            tipo_processo=tipo_processo,
            secao=secao,
            session=session,
        )

    def cjsg_parse(self, resultados_brutos: list) -> 'pd.DataFrame':
        """
        Extracts relevant data from the raw results returned by TJRS.
        Returns a DataFrame with the decisions.
        """
        return cjsg_parse_manager(resultados_brutos)

    def cjsg(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        classe: str = None,
        assunto: str = None,
        orgao_julgador: str = None,
        relator: str = None,
        data_julgamento_inicio: str = None,
        data_julgamento_fim: str = None,
        data_publicacao_inicio: str = None,
        data_publicacao_fim: str = None,
        tipo_processo: str = None,
        secao: str = None,
        session: 'requests.Session' = None,
        **kwargs,
    ) -> 'pd.DataFrame':
        """
        Fetches jurisprudence from TJRS in a simplified way (download + parse).
        Returns a ready-to-analyze DataFrame.
        """
        pesquisa_val = normalize_pesquisa(pesquisa, **kwargs)
        brutos = self.cjsg_download(
            pesquisa=pesquisa_val,
            paginas=paginas,
            classe=classe,
            assunto=assunto,
            orgao_julgador=orgao_julgador,
            relator=relator,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            tipo_processo=tipo_processo,
            secao=secao,
            session=session,
        )
        return self.cjsg_parse(brutos)
