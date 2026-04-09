"""Scraper for the Tribunal de Justica do Rio Grande do Norte (TJRN)."""
from typing import Union, List

import pandas as pd
import requests
from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_paginas, normalize_pesquisa, normalize_datas
from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


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
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        nr_processo: str = "",
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
        """Search TJRN jurisprudence.

        Parameters
        ----------
        pesquisa : str
            Free-text search term (searched in ementa).
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        nr_processo : str, optional
            Process number filter.
        id_classe_judicial : str, optional
            Judicial class ID.
        id_orgao_julgador : str, optional
            Judging body ID.
        id_relator : str, optional
            Reporter judge ID.
        id_colegiado : str, optional
            Collegiate body ID.
        sistema : str, optional
            ``"PJE"``, ``"SAJ"``, or empty for all.
        decisoes : str, optional
            ``"Monocraticas"``, ``"Colegiadas"``, ``"Sentencas"``, or empty for all.
        jurisdicoes : str, optional
            ``"Tribunal de Justica"``, ``"Turmas Recursais"``, or empty for all.
        grau : str, optional
            ``"1"`` (first), ``"2"`` (second), or empty for all.

        Returns
        -------
        pd.DataFrame
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(**kwargs)
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            nr_processo=nr_processo,
            id_classe_judicial=id_classe_judicial,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_colegiado=id_colegiado,
            dt_inicio=datas["data_julgamento_inicio"] or "",
            dt_fim=datas["data_julgamento_fim"] or "",
            sistema=sistema,
            decisoes=decisoes,
            jurisdicoes=jurisdicoes,
            grau=grau,
        )
        return self.cjsg_parse(brutos)

    def cjsg_download(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJRN.

        Parameters are the same as :meth:`cjsg`.

        Returns
        -------
        list
            List of raw JSON responses (one per page).
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        return cjsg_download_manager(
            pesquisa=pesquisa,
            paginas=paginas,
            session=self.session,
            **{k: v for k, v in kwargs.items() if k not in ("query", "termo")},
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
