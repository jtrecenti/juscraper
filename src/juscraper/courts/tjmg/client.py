"""Scraper for the Court of Justice of Minas Gerais (TJMG)."""
from __future__ import annotations

import logging
from typing import Literal

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse
from .schemas import InputCJSGTJMG

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
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        pesquisar_por: str = "ementa",
        order_by: str | int = 2,
        linhas_por_pagina: int = 10,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        **kwargs,
    ) -> list:
        """Run a TJMG acórdão search and return the raw HTML of each page.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

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
        inp = apply_input_pipeline_search(
            InputCJSGTJMG,
            "TJMGScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            pesquisar_por=pesquisar_por,
            order_by=order_by,
            linhas_por_pagina=linhas_por_pagina,
        )

        return _cjsg_download(
            session=self.session,
            pesquisa=inp.pesquisa or "",
            paginas=inp.paginas,
            pesquisar_por=inp.pesquisar_por,
            order_by=str(inp.order_by),
            data_julgamento_inicial=_br_date(inp.data_julgamento_inicio),
            data_julgamento_final=_br_date(inp.data_julgamento_fim),
            data_publicacao_inicial=_br_date(inp.data_publicacao_inicio),
            data_publicacao_final=_br_date(inp.data_publicacao_fim),
            linhas_por_pagina=inp.linhas_por_pagina,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJMG HTML pages into a DataFrame."""
        return _cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        pesquisar_por: Literal["ementa", "acordao"] = "ementa",
        order_by: str | int = 2,
        linhas_por_pagina: int = 10,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJMG (acordaos com captcha numerico).

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None`` (cap de 400 resultados, limite do TJMG).
            pesquisar_por ({"ementa", "acordao"}): Campo onde buscar.
                ``"acordao"`` busca no inteiro teor. Default ``"ementa"``.
            order_by (int | str): Ordenacao: ``2`` data julgamento,
                ``1`` data publicacao, ``0`` precisao. Default ``2``.
            linhas_por_pagina (int): Resultados por pagina (10, 20 ou 50).
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJMG`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``DD/MM/AAAA``. Backend: ``dataJulgamentoInicial`` /
                  ``dataJulgamentoFinal``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim`` (str):
                  ``DD/MM/AAAA``. Backend: ``dataPublicacaoInicial`` /
                  ``dataPublicacaoFinal``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: DataFrame com os acordaos.

        See also:
            :class:`InputCJSGTJMG` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            pesquisar_por=pesquisar_por,
            order_by=order_by,
            linhas_por_pagina=linhas_por_pagina,
            **kwargs,
        ))

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first degree case search not implemented for TJMG."""
        raise NotImplementedError("TJMG does not implement cpopg.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second degree case search not implemented for TJMG."""
        raise NotImplementedError("TJMG does not implement cposg.")


def _br_date(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        formatted: str = value.strftime("%d/%m/%Y")
        return formatted
    text = str(value).strip()
    if not text:
        return ""
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}/{text[5:7]}/{text[0:4]}"
    return text
