"""Pydantic schemas for TJPI scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjpi.client` — este arquivo e
documentacao executavel da API publica ate o TJPI ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJPIScraper.cjsg`.
"""
from __future__ import annotations

from ...schemas import OutputCJSGBase, SearchBase


class InputCJSGTJPI(SearchBase):
    """Accepted input for TJPI ``cjsg``.

    Endpoint HTML (JusPI, server-rendered). ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. O backend do TJPI nao expoe filtros de data — ao wirar
    este schema, passar ``data_*`` deve virar ``TypeError`` via
    ``extra="forbid"`` herdado de :class:`SearchBase`.
    """

    tipo: str = ""
    relator: str = ""
    classe: str = ""
    orgao: str = ""


class OutputCJSGTJPI(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJPIScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
