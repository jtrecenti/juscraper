"""Scraper for the Tribunal de Justica de Rondonia (TJRO)."""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_datas, normalize_paginas, normalize_pesquisa

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


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
        nr_processo: str = "",
        magistrado: str = "",
        orgao_julgador: int | str = "",
        orgao_julgador_colegiado: int | str = "",
        classe_judicial: str = "",
        instancia: list | None = None,
        termo_exato: bool = False,
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJRO jurisprudence.

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        tipo : list, optional
            Document types. Default ``["EMENTA"]``. Options include
            ``"ACORDAO"``, ``"DECISAO"``, ``"SENTENCA"``, ``"VOTO"``, etc.
        nr_processo : str, optional
            Process number filter.
        magistrado : str, optional
            Judge/magistrate name.
        orgao_julgador : int or str, optional
            Judging body ID.
        orgao_julgador_colegiado : int or str, optional
            Collegiate judging body ID.
        classe_judicial : str, optional
            Judicial class name.
        instancia : list, optional
            Jurisdiction grades (e.g. ``[1]``, ``[2]``, ``[1, 2]``).
        termo_exato : bool
            If True, search for exact term.

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
            tipo=tipo,
            nr_processo=nr_processo,
            magistrado=magistrado,
            orgao_julgador=orgao_julgador,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe_judicial=classe_judicial,
            data_julgamento_inicio=datas["data_julgamento_inicio"] or "",
            data_julgamento_fim=datas["data_julgamento_fim"] or "",
            instancia=instancia,
            termo_exato=termo_exato,
        )
        return self.cjsg_parse(brutos)

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJRO.

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

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
