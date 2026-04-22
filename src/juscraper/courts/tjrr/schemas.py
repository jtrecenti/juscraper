"""Pydantic schemas for TJRR scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjrr.client` — este arquivo e
documentacao executavel da API publica ate o TJRR ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJRRScraper.cjsg` / :meth:`TJRRScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJRR(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRR ``cjsg`` / ``cjsg_download``.

    Endpoint JSF/PrimeFaces com ViewState (jurisprudencia.tjrr.jus.br).
    ``pesquisa`` aceita os aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Apos a normalizacao, os kwargs que sobram caem aqui e
    sao rejeitados por ``extra="forbid"`` herdado de :class:`SearchBase`.
    Filtro de data de julgamento herdado de :class:`DataJulgamentoMixin`.
    """

    paginas: list[int] | range | None = None
    relator: str = ""
    orgao_julgador: list | None = None
    especie: list | None = None


class OutputCJSGTJRR(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRRScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
