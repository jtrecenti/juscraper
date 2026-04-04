"""
Scraper for the Tribunal de Justica do Espirito Santo (TJES).
"""
from typing import List, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_datas, normalize_paginas, normalize_pesquisa

from .download import CJPG_CORE, CJSG_CORES, DEFAULT_CORE, DEFAULT_PER_PAGE, cjsg_download
from .parse import cjsg_parse


class TJESScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Espirito Santo."""

    BASE_URL = "https://sistemas.tjes.jus.br/consulta-jurisprudencia/api"

    def __init__(self):
        super().__init__("TJES")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first-instance case lookup not implemented for TJES."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJES.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second-instance case lookup not implemented for TJES."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJES.")

    def cjsg_download(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        core: str = DEFAULT_CORE,
        busca_exata: bool = False,
        magistrado: str = None,
        orgao_julgador: str = None,
        classe_judicial: str = None,
        jurisdicao: str = None,
        assunto: str = None,
        ordenacao: str = None,
        per_page: int = DEFAULT_PER_PAGE,
        data_julgamento_inicio: str = None,
        data_julgamento_fim: str = None,
        data_publicacao_inicio: str = None,
        data_publicacao_fim: str = None,
        **kwargs,
    ) -> list:
        """
        Download raw JSON results from the TJES jurisprudence search.

        Parameters
        ----------
        pesquisa : str, optional
            Search term. ``query`` and ``termo`` are accepted as deprecated aliases.
        paginas : int, list, range, or None
            Pages to download (1-based). ``int`` n means pages 1..n.
            ``None`` downloads all available pages.
        core : str
            Solr core to query: ``pje2g`` (default), ``pje2g_mono``,
            ``legado``, ``turma_recursal_legado``. For first instance
            (``pje1g``), use :meth:`cjpg` instead.
        busca_exata : bool
            If True, perform exact-match search.
        magistrado : str
            Filter by judge name (exact, uppercase).
        orgao_julgador : str
            Filter by court division.
        classe_judicial : str
            Filter by judicial class.
        jurisdicao : str
            Filter by jurisdiction.
        assunto : str
            Filter by subject.
        ordenacao : str
            Sort expression (e.g. ``dt_juntada desc``).
        per_page : int
            Results per page (default 20).
        data_julgamento_inicio / data_julgamento_fim : str
            Date range filter (YYYY-MM-DD). TJES uses ``dataIni``/``dataFim`` which
            filters on ``dt_juntada``.

        Returns
        -------
        list
            Raw JSON responses, one per page.
        """
        if core not in CJSG_CORES:
            raise ValueError(
                f"cjsg nao suporta core='{core}'. Use um de: {', '.join(sorted(CJSG_CORES))}. "
                "Para primeiro grau (pje1g), use cjpg()."
            )
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        # TJES only supports a single date range (dataIni/dataFim mapped to dt_juntada)
        data_inicio = datas["data_julgamento_inicio"]
        data_fim = datas["data_julgamento_fim"]

        return cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            core=core,
            busca_exata=busca_exata,
            data_inicio=data_inicio,
            data_fim=data_fim,
            magistrado=magistrado,
            orgao_julgador=orgao_julgador,
            classe_judicial=classe_judicial,
            jurisdicao=jurisdicao,
            assunto=assunto,
            ordenacao=ordenacao,
            per_page=per_page,
            session=self.session,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """
        Parse raw TJES search results into a DataFrame.

        Parameters
        ----------
        resultados_brutos : list
            Raw JSON responses returned by :meth:`cjsg_download`.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse(resultados_brutos)

    def cjsg(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        core: str = DEFAULT_CORE,
        busca_exata: bool = False,
        magistrado: str = None,
        orgao_julgador: str = None,
        classe_judicial: str = None,
        jurisdicao: str = None,
        assunto: str = None,
        ordenacao: str = None,
        per_page: int = DEFAULT_PER_PAGE,
        data_julgamento_inicio: str = None,
        data_julgamento_fim: str = None,
        data_publicacao_inicio: str = None,
        data_publicacao_fim: str = None,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Search TJES jurisprudence (download + parse).

        Returns a ready-to-analyze DataFrame. Accepts all the same parameters
        as :meth:`cjsg_download`.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            core=core,
            busca_exata=busca_exata,
            magistrado=magistrado,
            orgao_julgador=orgao_julgador,
            classe_judicial=classe_judicial,
            jurisdicao=jurisdicao,
            assunto=assunto,
            ordenacao=ordenacao,
            per_page=per_page,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        return self.cjsg_parse(brutos)

    # --- cjpg (first instance / 1o grau) ---

    def _cjpg_download_internal(self, pesquisa, paginas, kwargs):
        """Shared logic for cjpg_download — delegates to cjsg_download with core=pje1g."""
        pesquisa_val = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(**kwargs)
        data_inicio = datas["data_julgamento_inicio"]
        data_fim = datas["data_julgamento_fim"]

        return cjsg_download(
            pesquisa=pesquisa_val,
            paginas=paginas,
            core=CJPG_CORE,
            busca_exata=kwargs.get("busca_exata", False),
            data_inicio=data_inicio,
            data_fim=data_fim,
            magistrado=kwargs.get("magistrado"),
            orgao_julgador=kwargs.get("orgao_julgador"),
            classe_judicial=kwargs.get("classe_judicial"),
            jurisdicao=kwargs.get("jurisdicao"),
            assunto=kwargs.get("assunto"),
            ordenacao=kwargs.get("ordenacao"),
            per_page=kwargs.get("per_page", DEFAULT_PER_PAGE),
            session=self.session,
        )

    def cjpg_download(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> list:
        """
        Download raw JSON results from the TJES first-instance search (core ``pje1g``).

        Accepts the same filter parameters as :meth:`cjsg_download` (except ``core``).

        Returns
        -------
        list
            Raw JSON responses, one per page.
        """
        return self._cjpg_download_internal(pesquisa, paginas, kwargs)

    def cjpg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """
        Parse raw TJES first-instance results into a DataFrame.

        Parameters
        ----------
        resultados_brutos : list
            Raw JSON responses returned by :meth:`cjpg_download`.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse(resultados_brutos)

    def cjpg(
        self,
        pesquisa: str = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Search TJES first-instance jurisprudence (download + parse).

        Shortcut for :meth:`cjpg_download` + :meth:`cjpg_parse`.
        Queries the ``pje1g`` core. Accepts the same filter parameters as
        :meth:`cjsg` (except ``core``).

        Returns
        -------
        pd.DataFrame
        """
        brutos = self._cjpg_download_internal(pesquisa, paginas, kwargs)
        return cjsg_parse(brutos)
