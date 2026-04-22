"""Pydantic schemas for TJMT scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjmt.client` — este arquivo e
documentacao executavel da API publica ate o TJMT ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJMTScraper.cjsg` / :meth:`TJMTScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJMT(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJMT ``cjsg`` / ``cjsg_download``.

    Endpoint REST JSON (hellsgate-preview). ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Datas aceitam os aliases ``data_inicio``/``data_fim``
    via :func:`juscraper.utils.params.normalize_datas`. Filtros de data
    herdados dos mixins.
    """

    tipo_consulta: str = "Acordao"
    relator: str | None = None
    orgao_julgador: str | None = None
    classe: str | None = None
    tipo_processo: str | None = None
    thesaurus: bool = False
    quantidade_por_pagina: int = 10


class OutputCJSGTJMT(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJMTScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
