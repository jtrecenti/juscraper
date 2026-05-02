"""Scraper for the Court of Justice of Goiás (TJGO)."""
from __future__ import annotations

import logging
from typing import List, Literal, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse
from .schemas import InputCJSGTJGO

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
        id_instancia: Literal[0, 1, 2, 3, "0", "1", "2", "3"] = 0,
        id_area: Literal[0, 1, 2, "0", "1", "2"] = 0,
        id_serventia_subtipo: Union[str, int] = 0,
        numero_processo: Optional[str] = None,
        qtde_itens_pagina: int = 10,
        data_publicacao_inicio: Optional[str] = None,
        data_publicacao_fim: Optional[str] = None,
        **kwargs,
    ) -> list:
        """Run a TJGO search and return the raw HTML of each page.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

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
        inp = apply_input_pipeline_search(
            InputCJSGTJGO,
            "TJGOScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            id_instancia=id_instancia,
            id_area=id_area,
            id_serventia_subtipo=id_serventia_subtipo,
            numero_processo=numero_processo,
            qtde_itens_pagina=qtde_itens_pagina,
        )

        return _cjsg_download(
            session=self.session,
            pesquisa=inp.pesquisa or "",
            paginas=inp.paginas,
            id_instancia=str(inp.id_instancia),
            id_area=str(inp.id_area),
            id_serventia_subtipo=str(inp.id_serventia_subtipo),
            data_publicacao_inicio=_br_date(inp.data_publicacao_inicio),
            data_publicacao_fim=_br_date(inp.data_publicacao_fim),
            numero_processo=inp.numero_processo or "",
            qtde_itens_pagina=inp.qtde_itens_pagina,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJGO HTML pages into a DataFrame."""
        return _cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        id_instancia: Literal[0, 1, 2, 3, "0", "1", "2", "3"] = 0,
        id_area: Literal[0, 1, 2, "0", "1", "2"] = 0,
        id_serventia_subtipo: Union[str, int] = 0,
        numero_processo: Optional[str] = None,
        qtde_itens_pagina: int = 10,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJGO (Projudi).

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            id_instancia (int | str): ``0`` todas / ``1`` 1o grau / ``2`` recursal /
                ``3`` tribunal.
            id_area (int | str): ``0`` todas / ``1`` civel / ``2`` criminal.
            id_serventia_subtipo (int | str): ID do subtipo de serventia
                (dropdown do site). ``0`` = todas.
            numero_processo (str): Filtrar por numero CNJ especifico.
            qtde_itens_pagina (int): Itens por pagina (default 10).
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJGO`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_publicacao_inicio`` / ``data_publicacao_fim`` (str):
                  ``DD/MM/AAAA`` ou ``AAAA-MM-DD``. Backend Projudi mapeia
                  para ``DataInicial`` / ``DataFinal`` no form body.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado, **incluindo**
                ``data_julgamento_inicio`` / ``data_julgamento_fim`` — o backend
                Projudi nao expoe filtro de data de julgamento; use
                ``data_publicacao_*`` (canonico para o TJGO).
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: DataFrame com as decisoes (coluna ``texto`` carrega
            o conteudo do documento; ``ementa`` nao e preenchido).

        See also:
            :class:`InputCJSGTJGO` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            id_instancia=id_instancia,
            id_area=id_area,
            id_serventia_subtipo=id_serventia_subtipo,
            numero_processo=numero_processo,
            qtde_itens_pagina=qtde_itens_pagina,
            **kwargs,
        ))

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
        formatted: str = value.strftime("%d/%m/%Y")
        return formatted
    text = str(value).strip()
    if not text:
        return ""
    # yyyy-mm-dd → dd/mm/yyyy
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}/{text[5:7]}/{text[0:4]}"
    return text
