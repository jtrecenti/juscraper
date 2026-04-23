"""Pydantic schemas for TJBA scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjba.client` — este arquivo e
documentacao executavel da API publica ate o TJBA ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJBAScraper.cjsg` / :meth:`TJBAScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataPublicacaoMixin, OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase


class InputCJSGTJBA(SearchBase, DataPublicacaoMixin):
    """Accepted input for TJBA ``cjsg`` / ``cjsg_download``.

    Endpoint GraphQL. ``pesquisa`` aceita os aliases deprecados ``query`` /
    ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`, que
    roda *antes* deste modelo. Apos a normalizacao, os kwargs que sobram
    caem aqui e sao rejeitados por ``extra="forbid"`` herdado de
    :class:`SearchBase`. Filtro de data de publicacao vem de
    :class:`DataPublicacaoMixin`.
    """

    numero_recurso: str | None = None
    orgaos: list | None = None
    relatores: list | None = None
    classes: list | None = None
    segundo_grau: bool = True
    turmas_recursais: bool = True
    tipo_acordaos: bool = True
    tipo_decisoes_monocraticas: bool = True
    ordenado_por: str = "dataPublicacao"
    items_per_page: int = 10


class OutputCJSGTJBA(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJBAScraper.cjsg`.

    Reflete ``tjba.parse.cjsg_parse`` — API GraphQL entrega ids separados
    (``relator_id``, ``orgao_julgador_id``, ``classe_id``).
    """

    relator_id: str | int | None = None
    orgao_julgador_id: str | int | None = None
    classe: str | None = None
    classe_id: str | int | None = None
    tipo_decisao: str | None = None
    hash: str | None = None
