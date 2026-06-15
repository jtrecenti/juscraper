"""Pydantic schemas for TJDFT scraper endpoints.

Wired em :mod:`juscraper.courts.tjdft.client` desde o lote L1 do #165 —
:meth:`TJDFTScraper.cjsg_download` valida kwargs via :class:`InputCJSGTJDFT`
com ``extra="forbid"`` herdado de :class:`SearchBase`.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, SearchBase


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
    inteiro_teor: bool = False
    tamanho_pagina: int = Field(default=10, ge=1)


class OutputCJSGTJDFT(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJDFTScraper.cjsg`.

    O parser do TJDFT (``tjdft.parse.cjsg_parse``) e passthrough do JSON
    da API: as chaves do DataFrame vem direto do backend. A base
    :class:`OutputCJSGBase` garante ``processo`` / ``ementa`` /
    ``data_julgamento``; demais campos fluem via ``extra='allow'``.
    """
