"""
Raspador para o Tribunal de Justiça do Distrito Federal e Territórios (TJDFT).
"""
from typing import Union, List
import pandas as pd
import requests
from .base_scraper import BaseScraper

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
        resultados = []
        if isinstance(paginas, int):
            paginas_iter = range(1, paginas+1)
        else:
            paginas_iter = paginas
        for pagina in paginas_iter:
            payload = {
                "query": query,
                "termosAcessorios": [],
                "pagina": pagina,  # começa do zero
                "tamanho": quantidade_por_pagina,
                "sinonimos": sinonimos,
                "espelho": espelho,
                "inteiroTeor": inteiro_teor,
                "retornaInteiroTeor": False,
                "retornaTotalizacao": True
            }
            headers = {
                "Content-Type": "application/json",
            }
            resp = requests.post(self.BASE_URL, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            resultados.extend(data.get("registros", []))
        return resultados

    def cjsg_parse(self, resultados_brutos: list) -> list:
        """
        Extrai informações estruturadas dos resultados brutos do TJDFT.
        Retorna todos os campos presentes em cada item.
        """
        return [dict(item) for item in resultados_brutos]

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
