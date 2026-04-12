"""Scraper for the Court of Justice of Goiás (TJGO)."""
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
    warn_unsupported,
)

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse

logger = logging.getLogger("juscraper.tjgo")


class TJGOScraper(BaseScraper):
    """Scraper for the Court of Justice of Goiás.

    The TJGO jurisprudence search (Projudi) renders a Cloudflare Turnstile
    widget, but the backend does not validate the token — the flow works
    with pure HTTP requests.
    """

    BASE_URL = "https://projudi.tjgo.jus.br/ConsultaJurisprudencia"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    def __init__(self, sleep_time: float = 1.0):
        super().__init__("TJGO")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self.sleep_time = sleep_time

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        id_instancia: Union[str, int] = 0,
        id_area: Union[str, int] = 0,
        id_serventia_subtipo: Union[str, int] = 0,
        numero_processo: str = "",
        qtde_itens_pagina: int = 10,
        **kwargs,
    ) -> list:
        """Run a TJGO search and return the raw HTML of each page.

        Parameters
        ----------
        pesquisa : str
            Free-text search term (aliases ``query`` / ``termo`` accepted).
        paginas : int, list, range or None
            Pages to download (1-based). ``None`` downloads every page.
        id_instancia : int or str
            ``0`` all / ``1`` 1st degree / ``2`` recursal / ``3`` tribunal.
        id_area : int or str
            ``0`` all / ``1`` civil / ``2`` criminal.
        id_serventia_subtipo : int or str
            Court unit sub-type id (see website dropdown). ``0`` = all.
        numero_processo : str
            Filter by specific CNJ process number.
        qtde_itens_pagina : int
            Items per page (default 10).
        data_publicacao_inicio, data_publicacao_fim : str, optional
            Publication date range in ``dd/mm/yyyy`` or ``yyyy-mm-dd``.
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        datas = normalize_datas(**kwargs)
        for key in ("data_julgamento_inicio", "data_julgamento_fim"):
            if datas[key] is not None:
                warn_unsupported(key, "TJGO")

        return _cjsg_download(
            session=self.session,
            pesquisa=pesquisa or "",
            paginas=paginas,
            id_instancia=str(id_instancia),
            id_area=str(id_area),
            id_serventia_subtipo=str(id_serventia_subtipo),
            data_publicacao_inicio=_br_date(datas["data_publicacao_inicio"]),
            data_publicacao_fim=_br_date(datas["data_publicacao_fim"]),
            numero_processo=numero_processo,
            qtde_itens_pagina=qtde_itens_pagina,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJGO HTML pages into a DataFrame."""
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
        """Stub: first degree case search not implemented for TJGO."""
        raise NotImplementedError("TJGO does not implement cpopg.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second degree case search not implemented for TJGO."""
        raise NotImplementedError("TJGO does not implement cposg.")


def _br_date(value) -> str:
    """Normalize a date-like value to TJGO's ``dd/mm/yyyy`` format."""
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    text = str(value).strip()
    if not text:
        return ""
    # yyyy-mm-dd → dd/mm/yyyy
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}/{text[5:7]}/{text[0:4]}"
    return text
