"""Pydantic schemas for TJSC scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjsc.client` — este arquivo e
documentacao executavel da API publica ate o TJSC ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJSCScraper.cjsg`.
"""
from __future__ import annotations

from typing import Literal

from ...schemas import (
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)


class InputCJSGTJSC(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJSC ``cjsg``.

    Endpoint HTML (eproc). ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Datas de julgamento e publicacao
    aceitam os aliases ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas`. Filtros de data
    herdados dos mixins.
    """

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
