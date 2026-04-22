"""Pydantic schemas for TJPA scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjpa.client` — este arquivo e
documentacao executavel da API publica ate o TJPA ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJPAScraper.cjsg` / :meth:`TJPAScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJPA(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJPA ``cjsg`` / ``cjsg_download``.

    Endpoint REST JSON (BFF). ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Datas aceitam os aliases
    ``data_inicio``/``data_fim`` via :func:`juscraper.utils.params.normalize_datas`.
    Filtros de data herdados dos mixins.
    """

    relator: str | None = None
    orgao_julgador_colegiado: str | None = None
    classe: str | None = None
    assunto: str | None = None
    origem: list | None = None
    tipo: list | None = None
    sort_by: str = "datajulgamento"
    sort_order: str = "desc"
    query_type: str = "free"
    query_scope: str = "ementa"


class OutputCJSGTJPA(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPAScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
