"""Pydantic schemas for TJES scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjes.client` — este arquivo e
documentacao executavel da API publica ate o TJES ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJESScraper.cjsg` / :meth:`TJESScraper.cjsg_download`
e :meth:`TJESScraper.cjpg` / :meth:`TJESScraper.cjpg_download`.
"""
from __future__ import annotations

from typing import Literal

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJES(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJES ``cjsg`` / ``cjsg_download``.

    Endpoint Elasticsearch (Solr) DSL. ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Apos a normalizacao, os kwargs que
    sobram caem aqui e sao rejeitados por ``extra="forbid"`` herdado de
    :class:`SearchBase`. Filtros de data herdados dos mixins.

    O parametro ``core`` e restrito aos cores de segundo grau; para primeiro
    grau (``pje1g``), use :class:`InputCJPGTJES`.
    """

    paginas: list[int] | range | None = None
    core: Literal["pje2g", "pje2g_mono", "legado", "turma_recursal_legado"] = "pje2g"
    busca_exata: bool = False
    magistrado: str | None = None
    orgao_julgador: str | None = None
    classe_judicial: str | None = None
    jurisdicao: str | None = None
    assunto: str | None = None
    ordenacao: str | None = None
    per_page: int = 20


class OutputCJSGTJES(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJESScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """


class InputCJPGTJES(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJES ``cjpg`` / ``cjpg_download``.

    Endpoint Elasticsearch (Solr) de primeiro grau — sempre usa o core
    ``pje1g``, por isso o campo ``core`` nao existe aqui. Aceita os mesmos
    filtros de :class:`InputCJSGTJES` (exceto ``core``) como kwargs.
    Filtros de data herdados dos mixins.
    """

    paginas: list[int] | range | None = None
    busca_exata: bool = False
    magistrado: str | None = None
    orgao_julgador: str | None = None
    classe_judicial: str | None = None
    jurisdicao: str | None = None
    assunto: str | None = None
    ordenacao: str | None = None
    per_page: int = 20


class OutputCJPGTJES(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJESScraper.cjpg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
