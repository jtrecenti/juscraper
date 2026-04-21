"""Pydantic schemas for TJSP cjsg and cjpg.

TJSP has a divergent public API from the 5 eSAJ-puros:

- ``cjsg``: uses ``baixar_sg: bool`` instead of ``origem: Literal["T","R"]``;
  drops ``numero_recurso`` and ``data_publicacao_*``.
- ``cjpg``: entirely different filter set (``classes`` plural, ``assuntos``
  plural, ``varas``, ``id_processo``); no ementa/classe/etc.

Both enforce a 120-char limit on ``pesquisa``. The length check happens
in ``client.py`` **before** building the pydantic model so the canonical
``QueryTooLongError`` propagates cleanly instead of being wrapped in
``pydantic.ValidationError``.
"""
from __future__ import annotations

from typing import Literal

from ...schemas.cjsg import SearchBase


class InputCJSGTJSP(SearchBase):
    """Accepted input for TJSP ``cjsg``. Unknown kwargs raise via ``extra='forbid'``."""

    ementa: str | None = None
    classe: str | None = None
    assunto: str | None = None
    comarca: str | None = None
    orgao_julgador: str | None = None
    baixar_sg: bool = True
    tipo_decisao: Literal["acordao", "monocratica"] = "acordao"


class InputCJPGTJSP(SearchBase):
    """Accepted input for TJSP ``cjpg``. Unknown kwargs raise via ``extra='forbid'``."""

    pesquisa: str = ""
    classes: list[str] | None = None
    assuntos: list[str] | None = None
    varas: list[str] | None = None
    id_processo: str | None = None
