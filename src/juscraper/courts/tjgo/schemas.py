"""Pydantic schemas for TJGO scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjgo.client` — este arquivo e
documentacao executavel da API publica ate o TJGO ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJGOScraper.cjsg` / :meth:`TJGOScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataPublicacaoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJGO(SearchBase, DataPublicacaoMixin):
    """Accepted input for TJGO ``cjsg`` / ``cjsg_download``.

    Endpoint HTML Projudi. ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Filtro de data de publicacao vem de
    :class:`DataPublicacaoMixin`; ``data_julgamento_*`` e emitido com
    ``warn_unsupported`` no client atual (excluido deste schema).
    """

    id_instancia: str | int = 0
    id_area: str | int = 0
    id_serventia_subtipo: str | int = 0
    numero_processo: str = ""
    qtde_itens_pagina: int = 10


class OutputCJSGTJGO(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJGOScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
