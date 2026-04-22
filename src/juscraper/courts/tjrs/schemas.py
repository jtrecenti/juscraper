"""Pydantic schemas for TJRS scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjrs.client` — este arquivo e
documentacao executavel da API publica ate o TJRS ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJRSScraper.cjsg` / :meth:`TJRSScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJRS(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJRS ``cjsg`` / ``cjsg_download``.

    Endpoint GSA (Google Search Appliance) com paginacao por offset.
    ``pesquisa`` aceita os aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Apos a normalizacao, os kwargs que sobram caem aqui e
    sao rejeitados por ``extra="forbid"`` herdado de :class:`SearchBase`.
    Filtros de data herdados dos mixins. O parametro ``session`` do
    metodo publico nao aparece aqui (dependencia de runtime, nao da API).
    """

    paginas: list[int] | range | None = None
    classe: str | None = None
    assunto: str | None = None
    orgao_julgador: str | None = None
    relator: str | None = None
    tipo_processo: str | None = None
    secao: str | None = None


class OutputCJSGTJRS(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRSScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
