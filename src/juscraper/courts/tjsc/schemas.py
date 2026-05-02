"""Pydantic schemas for TJSC scraper endpoints."""
from __future__ import annotations

from typing import ClassVar, Literal

from ...schemas import (
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)


class InputCJSGTJSC(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJSC ``cjsg`` / ``cjsg_download``.

    Wired em :meth:`juscraper.courts.tjsc.client.TJSCScraper.cjsg_download`
    desde o #183 — kwargs desconhecidos viram :class:`TypeError` em ambos
    ``cjsg`` e ``cjsg_download``. ``cjsg`` e wrapper trivial
    (``download → parse``).

    Endpoint HTML (eproc). ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Datas de julgamento e publicacao
    aceitam os aliases ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas`. Filtros de data
    herdados dos mixins. Backend espera ``YYYY-MM-DD``.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    campo: Literal["E", "I"] = "E"
    processo: str = ""


class OutputCJSGTJSC(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJSCScraper.cjsg`.

    Reflete ``tjsc.parse.cjsg_parse_manager`` — parser HTML do eproc.
    Quando o item traz apenas a ``decisao`` (e nao a ``ementa``), o parser
    usa o texto de ``decisao`` como ``ementa``.
    """

    classe: str | None = None
    uf: str | None = None
    decisao: str | None = None
