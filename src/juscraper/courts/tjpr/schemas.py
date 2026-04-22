"""Pydantic schemas for TJPR scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjpr.client` — este arquivo e
documentacao executavel da API publica ate o TJPR ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJPRScraper.cjsg` / :meth:`TJPRScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJPR(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJPR ``cjsg`` / ``cjsg_download``.

    Endpoint JSP custom do portal do TJPR. ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Apos a normalizacao, os kwargs que sobram caem aqui e
    sao rejeitados por ``extra="forbid"`` herdado de :class:`SearchBase`.
    Filtros de data herdados dos mixins.
    """

    paginas: list[int] | range | None = None


class OutputCJSGTJPR(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPRScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
