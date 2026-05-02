"""Scraper for the Court of Justice of Rio de Janeiro (TJRJ)."""
from __future__ import annotations

import logging

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import normalize_datas, normalize_paginas, normalize_pesquisa, warn_unsupported

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse

logger = logging.getLogger("juscraper.tjrj")


class TJRJScraper(BaseScraper):
    """Scraper for the Court of Justice of Rio de Janeiro.

    The TJRJ search form displays a reCAPTCHA widget, but the backend does
    not validate it — the entire flow works without solving anything.
    """

    BASE_URL = "https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    def __init__(self, sleep_time: float = 1.0):
        super().__init__("TJRJ")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self.sleep_time = sleep_time

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        ano_inicio: str | int | None = None,
        ano_fim: str | int | None = None,
        competencia: str = "1",
        origem: str = "1",
        tipo_acordao: bool = True,
        tipo_monocratica: bool = True,
        magistrado_codigo: str | None = None,
        orgao_codigo: str | None = None,
        **kwargs,
    ) -> list:
        """Run a TJRJ search and return the raw page payloads (list of dicts).

        Parameters
        ----------
        pesquisa : str
            Free-text search term. Aliases ``query`` / ``termo`` are accepted.
        paginas : int, list, range, or None
            Pages to download (1-based). ``None`` fetches every page.
        ano_inicio, ano_fim : str or int, optional
            Year range for judgment date. Defaults to blank (no filter).
        competencia : str
            ``"1"`` Cível / ``"2"`` Criminal / ``"3"`` ambos. Default ``"1"``.
        origem : str
            ``"1"`` 2º grau (default).
        tipo_acordao, tipo_monocratica : bool
            Whether to include acórdãos or monocratic decisions.
        magistrado_codigo, orgao_codigo : str, optional
            Comma-separated ids used by the site's tree selectors.
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(**kwargs)
        for key in ("data_julgamento_inicio", "data_julgamento_fim",
                    "data_publicacao_inicio", "data_publicacao_fim"):
            if datas[key] is not None:
                warn_unsupported(key, "TJRJ")
        ano_inicio_s = str(ano_inicio) if ano_inicio is not None else None
        ano_fim_s = str(ano_fim) if ano_fim is not None else None
        return _cjsg_download(
            session=self.session,
            pesquisa=pesquisa,
            paginas=paginas,
            ano_inicio=ano_inicio_s,
            ano_fim=ano_fim_s,
            competencia=competencia,
            origem=origem,
            tipo_acordao=tipo_acordao,
            tipo_monocratica=tipo_monocratica,
            magistrado_codigo=magistrado_codigo,
            orgao_codigo=orgao_codigo,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJRJ payloads into a DataFrame."""
        return _cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Convenience method: download + parse."""
        raw = self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        return self.cjsg_parse(raw)

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first degree case search not implemented for TJRJ."""
        raise NotImplementedError("TJRJ does not implement cpopg.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second degree case search not implemented for TJRJ."""
        raise NotImplementedError("TJRJ does not implement cposg.")
