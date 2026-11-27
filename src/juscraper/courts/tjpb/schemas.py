"""Pydantic schemas for TJPB scraper endpoints."""
from __future__ import annotations

from typing import ClassVar, Literal

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, SearchBase

# Dominios dos filtros de ``cjsg``, usados tambem nas assinaturas de ``TJPBScraper``.
IdOrigem = Literal["8", "2", "8,2"]


class InputCJSGTJPB(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJPB ``cjsg`` / ``cjsg_download``.

    Wired em :meth:`juscraper.courts.tjpb.client.TJPBScraper.cjsg_download`
    — kwargs desconhecidos viram :class:`TypeError` em ambos ``cjsg`` e
    ``cjsg_download``. ``cjsg`` e wrapper que adiciona post-filter local
    sobre ``data_julgamento`` (refs #195: o backend filtra por
    disponibilizacao, nao por ``dt_ementa``).

    Endpoint PJe-jurisprudencia (Laravel + Elasticsearch). ``pesquisa``
    aceita os aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Datas de julgamento aceitam os aliases
    ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas` (``data_publicacao_*``
    nao e suportado pelo backend e fica fora do schema). Filtro de data
    de julgamento herdado de :class:`DataJulgamentoMixin`. Backend espera
    ``YYYY-MM-DD``.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    numero_processo: str | None = None
    id_classe: str | None = None
    id_orgao_julgador: str | None = None
    id_relator: str | None = None
    # Valores de ``ids_jurisdicoes`` em ``/api/pje/origens/list``: ``"8"`` Turmas
    # Recursais, ``"2"`` Tribunal Pleno/Camaras/Secoes e ``"8,2"`` todas. A lista
    # separada por virgula e o formato do proprio backend, nao uma lista do usuario.
    id_origem: IdOrigem = "8,2"
    decisoes: bool = False


class OutputCJSGTJPB(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPBScraper.cjsg`.

    Reflete ``tjpb.parse.cjsg_parse_manager`` — o endpoint hoje entrega
    apenas ``processo``, ``ementa`` e ``data_julgamento`` (demais filtros
    nao viram colunas na resposta). Todos herdados de
    :class:`OutputCJSGBase`.
    """
