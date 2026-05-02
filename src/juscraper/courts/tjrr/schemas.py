"""Pydantic schemas for TJRR scraper endpoints.

Wired em :mod:`juscraper.courts.tjrr.client` via
:func:`juscraper.utils.params.apply_input_pipeline_search` (refs #93/#165).
A lista de campos bate byte-a-byte com a assinatura publica de
:meth:`TJRRScraper.cjsg` / :meth:`TJRRScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase


class InputCJSGTJRR(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRR ``cjsg`` / ``cjsg_download``.

    Endpoint JSF/PrimeFaces com ViewState (jurisprudencia.tjrr.jus.br).
    ``pesquisa`` aceita os aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Apos a normalizacao, os kwargs que sobram caem aqui e
    sao rejeitados por ``extra="forbid"`` herdado de :class:`SearchBase`.
    Filtro de data de julgamento herdado de :class:`DataJulgamentoMixin`.
    """

    relator: str = ""
    orgao_julgador: list | None = None
    especie: list | None = None


class OutputCJSGTJRR(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRRScraper.cjsg`.

    Reflete ``tjrr.parse.cjsg_parse_manager`` — parser HTML JSF/PrimeFaces.
    """

    classe: str | None = None
