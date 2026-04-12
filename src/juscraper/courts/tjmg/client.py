"""Scraper for the Court of Justice of Minas Gerais (TJMG)."""
from __future__ import annotations

import logging
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import (
    normalize_datas,
    normalize_paginas,
    normalize_pesquisa,
)

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse

logger = logging.getLogger("juscraper.tjmg")


class TJMGScraper(BaseScraper):
    """Scraper for the Court of Justice of Minas Gerais.

    The TJMG jurisprudence search uses a 5-digit numeric image captcha
    that is decoded with
    `txtcaptcha <https://github.com/jtrecenti/txtcaptcha>`_. Captcha
    validation is flagged once per session, so pagination reuses the
    same HTTP session after the first successful decoding.
    """

    BASE_URL = "https://www5.tjmg.jus.br/jurisprudencia"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    def __init__(self, sleep_time: float = 1.0):
        super().__init__("TJMG")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self.sleep_time = sleep_time

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        pesquisar_por: str = "ementa",
        order_by: Union[str, int] = 2,
        linhas_por_pagina: int = 10,
        **kwargs,
    ) -> list:
        """Run a TJMG acórdão search and return the raw HTML of each page.

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range or None
            Pages to download (1-based). ``None`` downloads every page
            (capped at 400 results, the TJMG limit).
        pesquisar_por : str
            Field to search in: ``"ementa"`` or ``"acordao"``
            (inteiro teor).
        order_by : int
            Sort order: ``2`` data julgamento, ``1`` data publicação,
            ``0`` precisão.
        linhas_por_pagina : int
            Results per page (10, 20 or 50).
        data_julgamento_inicio, data_julgamento_fim : str
            Julgamento date range (``dd/mm/yyyy`` or ``yyyy-mm-dd``).
        data_publicacao_inicio, data_publicacao_fim : str
            Publicação date range (``dd/mm/yyyy`` or ``yyyy-mm-dd``).
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(**kwargs)

        return _cjsg_download(
            session=self.session,
            pesquisa=pesquisa or "",
            paginas=paginas,
            pesquisar_por=pesquisar_por,
            order_by=str(order_by),
            data_julgamento_inicial=_br_date(datas["data_julgamento_inicio"]),
            data_julgamento_final=_br_date(datas["data_julgamento_fim"]),
            data_publicacao_inicial=_br_date(datas["data_publicacao_inicio"]),
            data_publicacao_final=_br_date(datas["data_publicacao_fim"]),
            linhas_por_pagina=linhas_por_pagina,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJMG HTML pages into a DataFrame."""
        return _cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Convenience method: download + parse."""
        raw = self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        return self.cjsg_parse(raw)

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first degree case search not implemented for TJMG."""
        raise NotImplementedError("TJMG does not implement cpopg.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second degree case search not implemented for TJMG."""
        raise NotImplementedError("TJMG does not implement cposg.")


def _br_date(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    text = str(value).strip()
    if not text:
        return ""
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}/{text[5:7]}/{text[0:4]}"
    return text
