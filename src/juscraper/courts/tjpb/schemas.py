"""Pydantic schemas for TJPB scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjpb.client` — este arquivo e
documentacao executavel da API publica ate o TJPB ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJPBScraper.cjsg`.
"""
from __future__ import annotations

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

    numero_processo: str | None = None
    id_classe: str | None = None
    id_orgao_julgador: str | None = None
    id_relator: str | None = None
    # TODO: investigar formato real (provavelmente list[str]) — refs follow-up de #184.
    id_origem: str = "8,2"
    decisoes: bool = False


class OutputCJSGTJPB(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPBScraper.cjsg`.

    Reflete ``tjpb.parse.cjsg_parse_manager`` — o endpoint hoje entrega
    apenas ``processo``, ``ementa`` e ``data_julgamento`` (demais filtros
    nao viram colunas na resposta). Todos herdados de
    :class:`OutputCJSGBase`.
    """
