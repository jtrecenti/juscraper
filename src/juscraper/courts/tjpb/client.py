"""Scraper for the Tribunal de Justica da Paraiba (TJPB)."""
from datetime import date
from typing import Union, List

import pandas as pd
import requests
from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_paginas, normalize_pesquisa, normalize_datas
from .download import cjsg_download_manager
from .parse import cjsg_parse_manager


def _parse_br(d: str) -> date | None:
    """Parse DD/MM/YYYY → date, tolerant to empty/None."""
    if not d:
        return None
    try:
        dd, mm, yy = d.split("/")
        return date(int(yy), int(mm), int(dd))
    except (ValueError, AttributeError):
        return None


class TJPBScraper(BaseScraper):
    """Scraper for the Tribunal de Justica da Paraiba (TJPB).

    Uses the PJe jurisprudence search at pje-jurisprudencia.tjpb.jus.br.
    Built on the same platform developed by TJRN (Laravel + Elasticsearch).
    """

    BASE_URL = "https://pje-jurisprudencia.tjpb.jus.br"

    def __init__(self):
        super().__init__("TJPB")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJPB."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJPB.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJPB."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJPB.")

    def cjsg(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        nr_processo: str = "",
        id_classe_judicial: str = "",
        id_orgao_julgador: str = "",
        id_relator: str = "",
        id_origem: str = "8,2",
        decisoes: bool = False,
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJPB jurisprudence.

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
        id_origem : str, optional
            Origin filter. ``"8,2"`` for all (default), ``"8"`` for Turmas Recursais,
            ``"2"`` for Tribunal Pleno/Camaras.
        decisoes : bool
            If True, include monocratic decisions.

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
            dt_inicio=datas["data_julgamento_inicio"] or "",
            dt_fim=datas["data_julgamento_fim"] or "",
            id_origem=id_origem,
            decisoes=decisoes,
        )
        df = self.cjsg_parse(brutos)

        # The TJPB backend filter on dt_inicio/dt_fim acts on an internal
        # disponibilização date, not on dt_ementa. Rows returned can have
        # dt_ementa far outside the requested window. Post-filter so the
        # returned data_julgamento (= dt_ementa) matches user intent.
        if not df.empty and "data_julgamento" in df.columns:
            start = _parse_br(datas["data_julgamento_inicio"])
            end = _parse_br(datas["data_julgamento_fim"])
            if start is not None and end is not None:
                mask = df["data_julgamento"].between(start, end)
                df = df[mask].reset_index(drop=True)
        return df

    def cjsg_download(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJPB.

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
