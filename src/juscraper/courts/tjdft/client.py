"""
Module for the scraper of the Court of Justice of the Federal District and Territories (TJDFT).
"""
from typing import List, Optional, Union

import pandas as pd

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, normalize_paginas, normalize_pesquisa

from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJDFT


class TJDFTScraper(BaseScraper):
    """Scraper for the Court of Justice of the Federal District and Territories (TJDFT)."""

    BASE_URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"

    def __init__(self):
        super().__init__("TJDFT")

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub for compatibility with BaseScraper."""
        raise NotImplementedError("TJDFT does not implement cpopg.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub for compatibility with BaseScraper."""
        raise NotImplementedError("TJDFT does not implement cposg.")

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        sinonimos: bool = True,
        espelho: bool = True,
        inteiro_teor: bool = False,
        quantidade_por_pagina: int = 10,
        **kwargs,
    ) -> list:
        """
        Downloads raw search results from the TJDFT jurisprudence search (using requests).
        Returns a list of raw results (JSON).

        Args:
            pesquisa: Search term. ``query`` is accepted as deprecated alias.
            paginas (int, list, range, or None): Pages to download (1-based).
                int: paginas=3 downloads pages 1-3.
                range: range(1, 4) downloads pages 1-3.
                None: downloads all available pages.
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        kwargs_local = dict(kwargs)
        inp = apply_input_pipeline_search(
            InputCJSGTJDFT,
            "TJDFTScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs_local,
            sinonimos=sinonimos,
            espelho=espelho,
            inteiro_teor=inteiro_teor,
            quantidade_por_pagina=quantidade_por_pagina,
        )
        brutos: list = cjsg_download(
            query=inp.pesquisa,
            paginas=inp.paginas,
            sinonimos=inp.sinonimos,
            espelho=inp.espelho,
            inteiro_teor=inp.inteiro_teor,
            quantidade_por_pagina=inp.quantidade_por_pagina,
            base_url=self.BASE_URL,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
        )
        return brutos

    def cjsg_parse(self, resultados_brutos: list) -> list:
        """
        Extracts structured information from the raw TJDFT search results.
        Returns all fields present in each item.
        """
        parsed: list = cjsg_parse(resultados_brutos)
        return parsed

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Searches for TJDFT jurisprudence in a simplified way (download + parse).
        Returns a ready-to-analyze DataFrame.
        """
        brutos = self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        dados = self.cjsg_parse(brutos)
        df = pd.DataFrame(dados)
        for col in ["data_julgamento", "data_publicacao"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df
