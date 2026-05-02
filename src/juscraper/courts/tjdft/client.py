"""
Module for the scraper of the Court of Justice of the Federal District and Territories (TJDFT).
"""

import pandas as pd

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJDFT


class TJDFTScraper(BaseScraper):
    """Scraper for the Court of Justice of the Federal District and Territories (TJDFT)."""

    BASE_URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"

    def __init__(self):
        super().__init__("TJDFT")

    def cpopg(self, id_cnj: str | list[str]):
        """Stub for compatibility with BaseScraper."""
        raise NotImplementedError("TJDFT does not implement cpopg.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub for compatibility with BaseScraper."""
        raise NotImplementedError("TJDFT does not implement cposg.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        sinonimos: bool = True,
        espelho: bool = True,
        inteiro_teor: bool = False,
        tamanho_pagina: int = 10,
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
            tamanho_pagina (int): Results per page (default 10). Aceita
                ``quantidade_por_pagina`` como alias deprecado.
        """
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "quantidade_por_pagina", "tamanho_pagina", tamanho_pagina, sentinel=10
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJDFT,
            "TJDFTScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            sinonimos=sinonimos,
            espelho=espelho,
            inteiro_teor=inteiro_teor,
            tamanho_pagina=tamanho_pagina,
        )
        brutos: list = cjsg_download(
            query=inp.pesquisa,
            paginas=inp.paginas,
            sinonimos=inp.sinonimos,
            espelho=inp.espelho,
            inteiro_teor=inp.inteiro_teor,
            quantidade_por_pagina=inp.tamanho_pagina,
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
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
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
