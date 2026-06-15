"""Pydantic schemas for TJPR scraper endpoints.

Wired em :meth:`juscraper.courts.tjpr.client.TJPRScraper.cjsg_download`
desde o lote L5 do #165 (relocalizado pelo #183) — kwargs desconhecidos
viram :class:`TypeError` em ambos ``cjsg`` e ``cjsg_download``. ``cjsg``
e wrapper trivial (``download → parse``).
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, OutputRelatoriaMixin, SearchBase


class InputCJSGTJPR(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJPR ``cjsg`` / ``cjsg_download``.

    Endpoint JSP custom do portal do TJPR. ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Apos a normalizacao, os kwargs que sobram caem aqui e
    sao rejeitados por ``extra="forbid"`` herdado de :class:`SearchBase`.
    Filtros de data herdados dos mixins.

    O TJPR nao expoe filtros estruturados alem de ``pesquisa``/``paginas``
    e datas — os demais filtros do portal sao parametros internos do
    fluxo JSP (session, jsessionid, etc.), nao parte da API publica.
    """


class OutputCJSGTJPR(OutputCJSGBase, OutputRelatoriaMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPRScraper.cjsg`.

    Reflete ``tjpr.parse.cjsg_parse`` — parser HTML do portal do TJPR.
    ``data_publicacao`` nao e extraida (apenas ``data_julgamento``).
    """
