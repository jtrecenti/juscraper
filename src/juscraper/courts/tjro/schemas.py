"""Pydantic schemas for TJRO scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjro.client` — este arquivo e
documentacao executavel da API publica ate o TJRO ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJROScraper.cjsg` / :meth:`TJROScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJRO(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRO ``cjsg`` / ``cjsg_download``.

    Endpoint Elasticsearch do JURIS (juris-back.tjro.jus.br) com paginacao
    por offset. ``pesquisa`` aceita os aliases deprecados ``query`` /
    ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`, que
    roda *antes* deste modelo. Apos a normalizacao, os kwargs que sobram
    caem aqui e sao rejeitados por ``extra="forbid"`` herdado de
    :class:`SearchBase`. Filtro de data de julgamento herdado de
    :class:`DataJulgamentoMixin`.
    """

    paginas: list[int] | range | None = None
    tipo: list | None = None
    nr_processo: str = ""
    magistrado: str = ""
    orgao_julgador: int | str = ""
    orgao_julgador_colegiado: int | str = ""
    classe_judicial: str = ""
    instancia: list | None = None
    termo_exato: bool = False


class OutputCJSGTJRO(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJROScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
