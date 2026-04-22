"""Pydantic schemas for TJPE scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjpe.client` — este arquivo e
documentacao executavel da API publica ate o TJPE ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJPEScraper.cjsg` / :meth:`TJPEScraper.cjsg_download`.
"""
from __future__ import annotations

from typing import Literal

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJPE(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJPE ``cjsg`` / ``cjsg_download``.

    Endpoint JSF/RichFaces com ViewState. ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Apos a normalizacao, os kwargs que sobram caem aqui e
    sao rejeitados por ``extra="forbid"`` herdado de :class:`SearchBase`.
    Filtro de data de julgamento herdado de :class:`DataJulgamentoMixin`.
    O parametro ``session`` do metodo publico nao aparece aqui (dependencia
    de runtime, nao da API).
    """

    paginas: list[int] | range | None = None
    relator: str | None = None
    classe_cnj: str | None = None
    assunto_cnj: str | None = None
    meio_tramitacao: str | None = None
    tipo_decisao: Literal["acordaos", "monocraticas", "todos"] = "acordaos"


class OutputCJSGTJPE(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPEScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
