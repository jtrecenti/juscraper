"""Scraper for the Tribunal de Justica de Mato Grosso do Sul (TJMS)."""
import logging
import shutil

import requests
from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_paginas, normalize_datas, validate_intervalo_datas

from .cjsg_download import cjsg_download as _cjsg_download
from .cjsg_parse import cjsg_n_pags, cjsg_parse_manager

logger = logging.getLogger("juscraper.tjms")


class TJMSScraper(BaseScraper):
    """Scraper for the Tribunal de Justica de Mato Grosso do Sul (TJMS).

    The TJMS uses the eSAJ platform (same as TJSP).
    Currently supports jurisprudence search (CJSG).
    """

    BASE_URL = "https://esaj.tjms.jus.br/"

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs,
    ):
        super().__init__("TJMS")
        self.session = requests.Session()
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time

    # --- cjsg (jurisprudencia 2o grau) ---

    def cjsg(
        self,
        pesquisa: str,
        paginas: int | list | range | None = None,
        ementa: str | None = None,
        numero_recurso: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        comarca: str | None = None,
        orgao_julgador: str | None = None,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        origem: str = "T",
        tipo_decisao: str = "acordao",
        **kwargs,
    ):
        """Search TJMS jurisprudence (2nd degree).

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        ementa : str, optional
            Filter by ementa text.
        numero_recurso : str, optional
            Appeal number filter.
        classe : str, optional
            Procedural class (tree selection value).
        assunto : str, optional
            Subject (tree selection value).
        comarca : str, optional
            District.
        orgao_julgador : str, optional
            Judging body (tree selection value).
        data_julgamento_inicio, data_julgamento_fim : str, optional
            Judgment date range (dd/mm/yyyy). Aliases: ``data_inicio``/``data_fim``.
        data_publicacao_inicio, data_publicacao_fim : str, optional
            Publication date range (dd/mm/yyyy).
        origem : str
            ``"T"`` for 2nd degree (default), ``"R"`` for recursal courts.
        tipo_decisao : str
            ``"acordao"`` or ``"monocratica"``.

        Returns
        -------
        pd.DataFrame
        """
        path = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            ementa=ementa,
            numero_recurso=numero_recurso,
            classe=classe,
            assunto=assunto,
            comarca=comarca,
            orgao_julgador=orgao_julgador,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            origem=origem,
            tipo_decisao=tipo_decisao,
            **kwargs,
        )
        result = self.cjsg_parse(path)
        shutil.rmtree(path)
        return result

    def cjsg_download(
        self,
        pesquisa: str,
        paginas: int | list | range | None = None,
        ementa: str | None = None,
        numero_recurso: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        comarca: str | None = None,
        orgao_julgador: str | None = None,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        origem: str = "T",
        tipo_decisao: str = "acordao",
        diretorio: str | None = None,
        **kwargs,
    ) -> str:
        """Download raw CJSG HTML result pages.

        Parameters are the same as :meth:`cjsg`, plus:

        diretorio : str, optional
            Directory to save files. Defaults to the scraper's download_path.

        Returns
        -------
        str
            Path to the directory containing HTML files.
        """
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        validate_intervalo_datas(
            datas["data_julgamento_inicio"],
            datas["data_julgamento_fim"],
            rotulo="data_julgamento",
        )
        validate_intervalo_datas(
            datas["data_publicacao_inicio"],
            datas["data_publicacao_fim"],
            rotulo="data_publicacao",
        )
        download_dir = diretorio or self.download_path
        return _cjsg_download(
            pesquisa=pesquisa,
            download_path=download_dir,
            sleep_time=self.sleep_time,
            ementa=ementa,
            numero_recurso=numero_recurso,
            classe=classe,
            assunto=assunto,
            comarca=comarca,
            orgao_julgador=orgao_julgador,
            data_julgamento_inicio=datas["data_julgamento_inicio"],
            data_julgamento_fim=datas["data_julgamento_fim"],
            data_publicacao_inicio=datas["data_publicacao_inicio"],
            data_publicacao_fim=datas["data_publicacao_fim"],
            origem=origem,
            tipo_decisao=tipo_decisao,
            paginas=paginas,
            get_n_pags_callback=cjsg_n_pags,
        )

    def cjsg_parse(self, diretorio: str):
        """Parse downloaded CJSG HTML files.

        Parameters
        ----------
        diretorio : str or Path
            Directory containing downloaded HTML files.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(diretorio)
