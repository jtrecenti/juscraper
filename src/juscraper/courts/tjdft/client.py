"""
Raspador para o Tribunal de Justiça do Distrito Federal e Territórios (TJDFT).
"""
from typing import Union, List
import pandas as pd
from juscraper.core.base import BaseScraper
from .download import cjsg_download
from .parse import cjsg_parse

class TJDFTScraper(BaseScraper):
    """Raspador para o Tribunal de Justiça do Distrito Federal e Territórios (TJDFT)."""
    BASE_URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"

    def __init__(self):
        super().__init__("TJDFT")

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub para compatibilidade com BaseScraper."""
        raise NotImplementedError("TJDFT não implementa cpopg.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub para compatibilidade com BaseScraper."""
        raise NotImplementedError("TJDFT não implementa cposg.")

    def cjsg_download(
        self,
        query: str,
        paginas: Union[int, list, range] = 0,
        sinonimos: bool = True,
        espelho: bool = True,
        inteiro_teor: bool = False,
        quantidade_por_pagina: int = 10,
    ) -> list:
        """
        Baixa resultados brutos da pesquisa de jurisprudência do TJDFT (usando requests).
        Retorna lista de resultados brutos (JSON).
        """
        return cjsg_download(
            query=query,
            paginas=paginas,
            sinonimos=sinonimos,
            espelho=espelho,
            inteiro_teor=inteiro_teor,
            quantidade_por_pagina=quantidade_por_pagina,
            base_url=self.BASE_URL
        )

    def cjsg_parse(self, resultados_brutos: list) -> list:
        """
        Extrai informações estruturadas dos resultados brutos do TJDFT.
        Retorna todos os campos presentes em cada item.
        """
        return cjsg_parse(resultados_brutos)

    def cjsg(self, query: str, paginas: Union[int, list, range] = 0) -> pd.DataFrame:
        """
        Busca jurisprudência do TJDFT de forma simplificada (download + parse).
        Retorna um DataFrame pronto para análise.
        """
        brutos = self.cjsg_download(query=query, paginas=paginas)
        dados = self.cjsg_parse(brutos)
        df = pd.DataFrame(dados)
        for col in ["data_julgamento", "data_publicacao"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df
