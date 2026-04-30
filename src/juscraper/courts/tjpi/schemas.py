"""Pydantic schemas for TJPI scraper endpoints."""
from __future__ import annotations

from ...schemas import OutputCJSGBase, SearchBase
from ...schemas.mixins import DataJulgamentoMixin


class InputCJSGTJPI(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJPI ``cjsg``.

    Endpoint HTML (JusPI, server-rendered). ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. ``data_julgamento_inicio``/``data_julgamento_fim``
    (ISO ``YYYY-MM-DD``) sao mapeados para ``data_min``/``data_max`` no
    GET pelo client (refs #94, #125). O backend nao expoe filtro de data
    de publicacao, entao ``DataPublicacaoMixin`` nao e herdado: passar
    ``data_publicacao_*`` levanta ``TypeError`` via ``extra="forbid"``.
    """

    tipo: str = ""
    relator: str = ""
    classe: str = ""
    orgao: str = ""


class OutputCJSGTJPI(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPIScraper.cjsg`.

    Reflete ``tjpi.parse.cjsg_parse_manager`` — parser HTML do JusPI.
    ``data_julgamento`` nao e extraido (apenas ``data_publicacao``).
    """

    tipo: str | None = None
    data_publicacao: str | None = None
    resumo: str | None = None
    inteiro_teor: str | None = None
    classe: str | None = None
    assunto: str | None = None
