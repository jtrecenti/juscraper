"""Pydantic schemas for TJAP scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjap.client` — este arquivo e
documentacao executavel da API publica ate o TJAP ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJAPScraper.cjsg` / :meth:`TJAPScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import OutputCJSGBase, SearchBase


class InputCJSGTJAP(SearchBase):
    """Accepted input for TJAP ``cjsg`` / ``cjsg_download``.

    Endpoint REST JSON da plataforma Tucujuris. ``pesquisa`` aceita os
    aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Apos a normalizacao, os kwargs que sobram caem aqui e
    sao rejeitados por ``extra="forbid"`` herdado de :class:`SearchBase`.
    """

    paginas: list[int] | range | None = None
    orgao: str = "0"
    numero_cnj: str | None = None
    numero_acordao: str | None = None
    numero_ano: str | None = None
    palavras_exatas: bool = False
    relator: str | None = None
    secretaria: str | None = None
    classe: str | None = None
    votacao: str = "0"
    origem: str | None = None


class OutputCJSGTJAP(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJAPScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
