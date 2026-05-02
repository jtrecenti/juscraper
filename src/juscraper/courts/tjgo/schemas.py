"""Pydantic schemas for TJGO scraper endpoints.

Wired em :mod:`juscraper.courts.tjgo.client` via
:func:`juscraper.utils.params.apply_input_pipeline_search` (refs #93/#165).
A lista de campos bate byte-a-byte com a assinatura publica de
:meth:`TJGOScraper.cjsg` / :meth:`TJGOScraper.cjsg_download`.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from ...schemas import DataPublicacaoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJGO(SearchBase, DataPublicacaoMixin):
    """Accepted input for TJGO ``cjsg`` / ``cjsg_download``.

    Endpoint HTML Projudi. ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Filtro de data de publicacao vem de
    :class:`DataPublicacaoMixin`; o backend Projudi nao expoe filtro de data
    de julgamento — passar ``data_julgamento_inicio`` / ``data_julgamento_fim``
    levanta :class:`TypeError` via ``extra="forbid"`` herdado de
    :class:`SearchBase`.

    A API publica do TJGO aceita datas em ISO (``YYYY-MM-DD``); o client
    converte para o formato BR (``DD/MM/YYYY``) esperado pelo Projudi via
    ``_br_date`` antes do POST.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    id_instancia: Literal[0, 1, 2, 3, "0", "1", "2", "3"] = 0
    id_area: Literal[0, 1, 2, "0", "1", "2"] = 0
    # TODO (#212): apertar com Literal[...] após captura do dropdown do site.
    id_serventia_subtipo: str | int = 0
    numero_processo: str | None = None
    qtde_itens_pagina: int = Field(default=10, ge=1)


class OutputCJSGTJGO(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJGOScraper.cjsg`.

    O parser do TJGO (``src/juscraper/courts/tjgo/parse.py``) entrega o
    conteudo do documento na coluna ``texto``, nao em ``ementa`` — diferente
    dos demais cjsg. ``OutputCJSGBase.ementa`` ja e Optional, entao o TJGO
    apenas nao preenche ``ementa``.
    """

    id_arquivo: str | None = None
    serventia: str | None = None
    relator: str | None = None
    tipo_ato: str | None = None
    data_publicacao: str | None = None
    texto: str | None = None
