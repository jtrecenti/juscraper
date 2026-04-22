"""Pydantic schemas for TJDFT scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjdft.client` — este arquivo e
documentacao executavel da API publica ate o TJDFT ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJDFTScraper.cjsg` / :meth:`TJDFTScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import OutputCJSGBase, SearchBase


class InputCJSGTJDFT(SearchBase):
    """Accepted input for TJDFT ``cjsg`` / ``cjsg_download``.

    Endpoint REST JSON. ``pesquisa`` aceita o alias deprecado ``query`` via
    :func:`juscraper.utils.params.normalize_pesquisa` (roda antes deste
    modelo). O TJDFT nao suporta filtros de data — ao wirar este schema,
    passar ``data_*`` deve virar ``TypeError`` via ``extra="forbid"`` (hoje
    o comportamento equivalente e ``warn_unsupported``).
    """

    sinonimos: bool = True
    espelho: bool = True
    inteiro_teor: bool = False
    quantidade_por_pagina: int = 10


class OutputCJSGTJDFT(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJDFTScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
