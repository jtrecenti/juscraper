"""Pydantic schemas for TJPB scraper endpoints.

Wired em :meth:`juscraper.courts.tjpb.client.TJPBScraper.cjsg` desde o
lote L4 do #165 — kwargs desconhecidos viram :class:`TypeError`.
"""
from __future__ import annotations

from typing import ClassVar

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJPB(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJPB ``cjsg``.

    Endpoint PJe-jurisprudencia (Laravel + Elasticsearch). ``pesquisa``
    aceita os aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Datas de julgamento aceitam os aliases
    ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas` (``data_publicacao_*``
    nao e suportado pelo backend e fica fora do schema). Filtro de data
    de julgamento herdado de :class:`DataJulgamentoMixin`.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    numero_processo: str = ""
    id_classe_judicial: str = ""
    id_orgao_julgador: str = ""
    id_relator: str = ""
    id_origem: str = "8,2"
    decisoes: bool = False


class OutputCJSGTJPB(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPBScraper.cjsg`.

    Reflete ``tjpb.parse.cjsg_parse_manager`` — o endpoint hoje entrega
    apenas ``processo``, ``ementa`` e ``data_julgamento`` (demais filtros
    nao viram colunas na resposta). Todos herdados de
    :class:`OutputCJSGBase`.
    """
