"""Scraper for the Court of Justice of Goiás (TJGO)."""
from __future__ import annotations

import logging
from datetime import date
from typing import Literal

import pandas as pd
import requests

from juscraper.core.avisos import avisar
from juscraper.core.http import HTTPScraper
from juscraper.utils.deprecacao import resolve_deprecated_value
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse
from .schemas import InputCJSGTJGO

logger = logging.getLogger("juscraper.tjgo")

# Opcoes do seletor "Instancia" e, ate a 0.7.0, os valores deprecados 1, 2 e 3.
IdInstancia = Literal[0, 15, 151, 1, 2, 3, "0", "15", "151", "1", "2", "3"]


class TJGOScraper(HTTPScraper):
    """Scraper for the Court of Justice of Goiás.

    A busca de jurisprudencia do TJGO (Projudi) tem um widget Cloudflare
    Turnstile. Desde 12/11/2026 (Projudi 3.194.1) o servidor valida o token, que
    o raspador nao envia: toda busca volta vazia, e ``cjsg``/``cjsg_download``
    emitem ``UserWarning`` explicando o bloqueio.
    """

    BASE_URL = "https://projudi.tjgo.jus.br/ConsultaJurisprudencia"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    def __init__(self, sleep_time: float = 1.0):
        super().__init__("TJGO", sleep_time=sleep_time)

    def _configure_session(self, session: requests.Session) -> None:
        session.headers["User-Agent"] = self.USER_AGENT

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        id_instancia: IdInstancia = 0,
        id_area: Literal[0, 1, 2, "0", "1", "2"] = 0,
        id_serventia_subtipo: str | int = 0,
        numero_processo: str | None = None,
        tamanho_pagina: int = 10,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
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
            ``0`` all / ``15`` tribunal / ``151`` turmas recursais. ``2`` and
            ``3`` are deprecated aliases of ``151`` and ``15``; ``1`` is
            deprecated with no replacement.
        id_area : int or str
            ``0`` all / ``1`` civil / ``2`` criminal. With ``id_instancia=151``
            only ``0`` is accepted, as in the website form.
        id_serventia_subtipo : int or str
            Code from the website's "Orgao" dropdown (e.g. ``14`` civil
            chambers, ``20`` criminal chambers). ``0`` = all. A code the form
            does not list for the chosen instance and area raises
            ``ValidationError``.
        numero_processo : str
            Filter by specific CNJ process number.
        tamanho_pagina : int
            Items per page (default 10). Aceita ``qtde_itens_pagina`` como
            alias deprecado.
        data_publicacao_inicio, data_publicacao_fim : str, date or None
            Publication date range: ``DD/MM/AAAA``, ``DD-MM-AAAA``,
            ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
        """
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "qtde_itens_pagina", "tamanho_pagina", tamanho_pagina, sentinel=10
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJGO,
            "TJGOScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            id_instancia=_resolver_id_instancia(id_instancia),
            id_area=id_area,
            id_serventia_subtipo=id_serventia_subtipo,
            numero_processo=numero_processo,
            tamanho_pagina=tamanho_pagina,
        )

        return _cjsg_download(
            request_fn=self._request_with_retry,
            pesquisa=inp.pesquisa or "",
            paginas=inp.paginas,
            id_instancia=str(inp.id_instancia),
            id_area=str(inp.id_area),
            id_serventia_subtipo=str(inp.id_serventia_subtipo),
            data_publicacao_inicio=_br_date(inp.data_publicacao_inicio),
            data_publicacao_fim=_br_date(inp.data_publicacao_fim),
            numero_processo=inp.numero_processo or "",
            qtde_itens_pagina=inp.tamanho_pagina,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJGO HTML pages into a DataFrame."""
        return _cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        id_instancia: IdInstancia = 0,
        id_area: Literal[0, 1, 2, "0", "1", "2"] = 0,
        id_serventia_subtipo: str | int = 0,
        numero_processo: str | None = None,
        tamanho_pagina: int = 10,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJGO (Projudi).

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            id_instancia (int | str): ``0`` todas / ``15`` Tribunal / ``151``
                Turma de Uniformizacao e Turmas Recursais, as opcoes do
                seletor "Instancia" do site. ``1``, ``2`` e ``3`` sao
                deprecados (ver abaixo); o 1o grau nao esta no seletor, e
                ``1`` vai ao portal como esta.
            id_area (int | str): ``0`` todas / ``1`` civel / ``2`` criminal.
                Com ``id_instancia=151``, so ``0``, como no formulario do site.
            id_serventia_subtipo (int | str): Codigo do seletor "Orgao" do
                site (por exemplo, ``14`` Camaras Civeis, ``20`` Camaras
                Criminais, ``6`` Turma Recursal Civel e Criminal). ``0`` =
                todos. Codigo fora da lista, ou que o formulario nao oferece
                para a instancia e a area escolhidas, levanta ``ValidationError``.
            numero_processo (str): Filtrar por numero CNJ especifico.
            tamanho_pagina (int): Itens por pagina (default 10).
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJGO`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str | date | None): ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
                  Backend Projudi mapeia
                  para ``DataInicial`` / ``DataFinal`` no form body.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``
            * ``qtde_itens_pagina`` -> ``tamanho_pagina``
            * ``id_instancia=2`` -> ``id_instancia=151``; ``id_instancia=3`` ->
              ``id_instancia=15``; ``id_instancia=1`` sem substituto

        Raises:
            TypeError: Quando um kwarg desconhecido e passado, **incluindo**
                ``data_julgamento_inicio`` / ``data_julgamento_fim`` — o backend
                Projudi nao expoe filtro de data de julgamento; use
                ``data_publicacao_*`` (canonico para o TJGO).
            ValidationError: Quando um filtro tem formato invalido ou a
                combinacao de ``id_instancia``, ``id_area`` e
                ``id_serventia_subtipo`` nao existe no formulario do Projudi.

        Returns:
            DataFrame com as decisoes (coluna ``texto`` carrega
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
            tamanho_pagina=tamanho_pagina,
            **kwargs,
        ))

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first degree case search not implemented for TJGO."""
        raise NotImplementedError("TJGO does not implement cpopg.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second degree case search not implemented for TJGO."""
        raise NotImplementedError("TJGO does not implement cposg.")


# Valores que a docstring indicava ate a 0.5.0 ("1 1o grau", "2 recursal",
# "3 tribunal"), fora das opcoes do seletor "Instancia" do Projudi, e a opcao
# equivalente. O formulario atual nao tem o 1o grau: ``1`` vai como esta.
_ID_INSTANCIA_DEPRECADO: dict[str, int | str] = {"2": 151, "3": 15}
_SO_OPCOES_DO_FORM = (
    "o formulario do Projudi so oferece 0 (todas), 15 (Tribunal) e 151 (Turmas Recursais)."
)


def _resolver_id_instancia(id_instancia: int | str) -> int | str:
    """Troca ``2``/``3`` pela opcao do formulario e avisa de ``1``, com ``DeprecationWarning``."""
    if str(id_instancia) == "1":
        avisar(
            f"id_instancia={id_instancia!r} esta deprecado: {_SO_OPCOES_DO_FORM} "
            "O valor (1o grau) vai ao portal como esta, sem garantia de filtro.",
            DeprecationWarning,
        )
        return id_instancia
    return resolve_deprecated_value(
        id_instancia,
        _ID_INSTANCIA_DEPRECADO,
        "id_instancia={antigo!r} esta deprecado: " + _SO_OPCOES_DO_FORM
        + " O juscraper passa a enviar {novo}; use id_instancia={novo}.",
    )


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
