"""Pydantic schemas for STF scraper endpoints.

Wired em :mod:`juscraper.courts.stf.client`: :meth:`STFScraper.listar_decisoes` e
:meth:`STFScraper.contar_decisoes` validam kwargs com ``extra="forbid"`` herdado
de :class:`SearchBase`.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ...schemas import BuscarEm, DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, SearchBase, TamanhoPagina
from ...schemas.mixins import OutputDataPublicacaoMixin, OutputRelatoriaMixin
from .download import MAX_TAMANHO_PAGINA


class _InputFiltrosSTF(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Filtros comuns a ``listar_decisoes`` e ``contar_decisoes``.

    Datas saem para o backend em ``ddMMyyyy``, formato dos filtros ``range`` do portal.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%d%m%Y"

    base: Literal["decisoes", "acordaos"] = "decisoes"
    classe: str | list[str] | None = None
    buscar_em: BuscarEm = "ementa"


class InputListarDecisoesSTF(_InputFiltrosSTF):
    """Accepted input for :meth:`STFScraper.listar_decisoes`.

    Filtros de :class:`_InputFiltrosSTF`, mais o tamanho da pagina e o
    checkpoint. O client passa ``pesquisa="*"`` quando o usuario nao informa
    termo, e a busca devolve tudo o que os filtros selecionam.
    """

    tamanho_pagina: TamanhoPagina = Field(default=MAX_TAMANHO_PAGINA, le=MAX_TAMANHO_PAGINA)
    checkpoint_dir: str | Path | None = None
    resume: bool = False


class InputContarDecisoesSTF(_InputFiltrosSTF):
    """Accepted input for :meth:`STFScraper.contar_decisoes`.

    Filtros de :class:`_InputFiltrosSTF`, os mesmos de
    :class:`InputListarDecisoesSTF`, sem ``tamanho_pagina`` nem checkpoint.
    """


class OutputListarDecisoesSTF(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`STFScraper.listar_decisoes`.

    O parser renomeia as chaves canonicas e repassa o resto do ``_source`` da API
    via ``extra="allow"``. ``ementa`` so vem preenchida em acordaos; o texto das
    monocraticas vem em ``decisao_texto``.
    """

    classe: str | None = None
    base: str | None = None
    decisao_texto: str | None = None
    inteiro_teor_url: str | None = None


class OutputContarDecisoesSTF(BaseModel):
    """Uma linha do DataFrame de :meth:`STFScraper.contar_decisoes`.

    ``faceta="total"`` traz o total da busca com ``valor=None``; as demais linhas sao
    buckets das agregacoes do portal.
    """

    faceta: str
    valor: str | None = None
    n: int

    model_config = ConfigDict(extra="allow")
