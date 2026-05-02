"""Pydantic schemas for TJPA scraper endpoints."""
from __future__ import annotations

from datetime import date
from typing import ClassVar, Literal

from ...schemas import (
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)


class InputCJSGTJPA(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJPA ``cjsg`` / ``cjsg_download``.

    Wired em :meth:`juscraper.courts.tjpa.client.TJPAScraper.cjsg_download`
    desde o #183 (eliminada duplicacao do pipeline em ``cjsg``) — kwargs
    desconhecidos viram :class:`TypeError` em ambos ``cjsg`` e
    ``cjsg_download``. ``cjsg`` e wrapper trivial (``download → parse``).

    Endpoint REST JSON (BFF). ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Datas aceitam os aliases
    ``data_inicio``/``data_fim`` via :func:`juscraper.utils.params.normalize_datas`.
    Filtros de data herdados dos mixins. Backend espera ``YYYY-MM-DD``.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    relator: str | None = None
    orgao_julgador_colegiado: str | None = None
    classe: str | None = None
    assunto: str | None = None
    origem: list | None = None
    tipo: list | None = None
    # TODO: apertar com Literal[...] após captura do BFF — refs follow-up de #184.
    sort_by: str = "datajulgamento"
    sort_order: Literal["asc", "desc"] = "desc"
    # TODO: apertar com Literal[...] após captura do BFF — refs follow-up de #184.
    query_type: str = "free"
    # TODO: apertar com Literal[...] após captura do BFF — refs follow-up de #184.
    query_scope: str = "ementa"


class OutputCJSGTJPA(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPAScraper.cjsg`.

    Reflete ``tjpa.parse.cjsg_parse_manager``. ``assunto`` vem como string
    com multiplas entradas separadas por ``"; "`` (parser concatena dicts).
    """

    id: int | str | None = None
    tipo: str | None = None
    area: str | None = None
    origem: str | None = None
    classe: str | None = None
    id_classe: str | int | None = None
    assunto: str | None = None
    id_assunto: str | int | None = None
    orgao_julgador_colegiado: str | None = None
    competencia: str | None = None
    data_documento: date | str | None = None
    sentido_decisao: str | None = None
    especie: str | None = None
    sistema_origem: str | None = None
    hash_storage: str | None = None
