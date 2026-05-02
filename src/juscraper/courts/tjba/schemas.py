"""Pydantic schemas for TJBA scraper endpoints.

Wired em :mod:`juscraper.courts.tjba.client` desde o lote L2 do #165 —
:meth:`TJBAScraper.cjsg_download` valida kwargs via :class:`InputCJSGTJBA`
com ``extra="forbid"`` herdado de :class:`SearchBase`.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from ...schemas import DataPublicacaoMixin, OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase


class InputCJSGTJBA(SearchBase, DataPublicacaoMixin):
    """Accepted input for TJBA ``cjsg`` / ``cjsg_download``.

    Endpoint GraphQL. ``pesquisa`` aceita os aliases deprecados ``query`` /
    ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`, que
    roda *antes* deste modelo. Apos a normalizacao, os kwargs que sobram
    caem aqui e sao rejeitados por ``extra="forbid"`` herdado de
    :class:`SearchBase`. Filtro de data de publicacao vem de
    :class:`DataPublicacaoMixin`.

    ``BACKEND_DATE_FORMAT="%Y-%m-%d"`` (ISO) — o backend GraphQL aceita
    datas em ``YYYY-MM-DD``, entao :func:`apply_input_pipeline_search`
    coage as datas para esse formato antes de validar (refs #173).
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    numero_recurso: str | None = None
    orgaos: list | None = None
    relatores: list | None = None
    classes: list | None = None
    segundo_grau: bool = True
    turmas_recursais: bool = True
    tipo_acordaos: bool = True
    tipo_decisoes_monocraticas: bool = True
    # TODO (#212): apertar com Literal[...] após captura do GraphQL.
    ordenado_por: str = "dataPublicacao"
    items_per_page: int = Field(default=10, ge=1)


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
