"""Pydantic schemas for TJDFT scraper endpoints.

Wired em :mod:`juscraper.courts.tjdft.client` desde o lote L1 do #165 —
:meth:`TJDFTScraper.cjsg_download` valida kwargs via :class:`InputCJSGTJDFT`
com ``extra="forbid"`` herdado de :class:`SearchBase`.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from ...schemas import (
    BuscarEm,
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
    TamanhoPagina,
)
from .download import MAX_TAMANHO_PAGINA


class InputCJSGTJDFT(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJDFT ``cjsg`` / ``cjsg_download``.

    Endpoint REST JSON. ``pesquisa`` aceita o alias deprecado ``query`` via
    :func:`juscraper.utils.params.normalize_pesquisa` (roda antes deste
    modelo). Os filtros de data (``data_julgamento_*`` / ``data_publicacao_*``)
    sao traduzidos pelo download para entradas do array ``termosAcessorios``
    no payload JSON da API.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    sinonimos: bool = True
    espelho: bool = True
    # O portal recebe ``inteiroTeor``: ``True`` soma o inteiro teor ao espelho.
    buscar_em: BuscarEm = "ementa"
    tamanho_pagina: TamanhoPagina = Field(default=10, le=MAX_TAMANHO_PAGINA)


class OutputCJSGTJDFT(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJDFTScraper.cjsg`.

    O parser (``tjdft.parse.cjsg_parse``) dá nome canônico a relator, órgão
    julgador e datas, e repassa as demais chaves da API via ``extra='allow'``.
    """
