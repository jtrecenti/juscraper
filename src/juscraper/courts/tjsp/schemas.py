"""Pydantic schemas for TJSP cjsg, cjpg, cpopg and cposg.

TJSP has a divergent public API from the 5 eSAJ-puros:

- ``cjsg``: uses ``baixar_sg: bool`` instead of ``origem: Literal["T","R"]``;
  drops ``numero_recurso`` and ``data_publicacao_*``.
- ``cjpg``: entirely different filter set (``classes`` plural, ``assuntos``
  plural, ``varas``, ``id_processo``); no ementa/classe/etc.
- ``cpopg`` / ``cposg``: consulta processual com chaveamento
  ``method="html"|"api"``, unico no TJSP.

``cjsg`` e ``cjpg`` reforcam um limite de 120 caracteres em ``pesquisa``.
A verificacao de tamanho acontece em ``client.py`` **antes** de construir
o modelo pydantic para que o ``QueryTooLongError`` canonico propague
limpo em vez de ser embrulhado em ``pydantic.ValidationError``.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ...schemas import CnjInputBase, DataJulgamentoMixin, OutputCnjConsultaBase, SearchBase
from ...schemas.cjsg import OutputCJSGBase


class InputCJSGTJSP(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJSP ``cjsg``. Unknown kwargs raise via ``extra='forbid'``.

    Herda filtro de data de julgamento via :class:`DataJulgamentoMixin`.
    TJSP **nao** suporta ``data_publicacao_*`` nem ``numero_recurso``.
    """

    ementa: str | None = None
    classe: str | None = None
    assunto: str | None = None
    comarca: str | None = None
    orgao_julgador: str | None = None
    baixar_sg: bool = True
    tipo_decisao: Literal["acordao", "monocratica"] = "acordao"


class OutputCJSGTJSP(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJSPScraper.cjsg`.

    Herda ``processo``, ``ementa`` e ``data_julgamento`` de
    :class:`OutputCJSGBase` e acrescenta colunas canonicas do parser
    eSAJ compartilhado (``cd_acordao``, ``relator``, ``orgao_julgador``).

    Provisorio — revisar quando samples forem capturados (refs #113).
    """

    cd_acordao: str | None = None
    relator: str | None = None
    orgao_julgador: str | None = None


class InputCJPGTJSP(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJSP ``cjpg``. Unknown kwargs raise via ``extra='forbid'``.

    Sobrescreve ``pesquisa`` com default vazio porque o TJSP permite buscar
    so por filtros (ex.: ``classes=[...]``) sem termo textual.
    """

    pesquisa: str = ""
    classes: list[str] | None = None
    assuntos: list[str] | None = None
    varas: list[str] | None = None
    id_processo: str | None = None


class OutputCJPGTJSP(BaseModel):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJSPScraper.cjpg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """

    id_processo: str
    cd_processo: str | None = None

    model_config = ConfigDict(extra="allow")


class InputCPOPGTJSP(CnjInputBase):
    """Accepted input for :meth:`TJSPScraper.cpopg`.

    O TJSP oferece dois caminhos (``method='html'`` via eSAJ e
    ``method='api'`` via ``api.tjsp.jus.br``). O schema documenta a
    assinatura publica — ele ainda nao esta wired no client.
    """

    method: Literal["html", "api"] = "html"


class OutputCPOPGTJSP(OutputCnjConsultaBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJSPScraper.cpopg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """


class InputCPOSGTJSP(CnjInputBase):
    """Accepted input for :meth:`TJSPScraper.cposg`.

    Como em ``cpopg``, o TJSP aceita ``method='html'`` ou ``method='api'``.
    """

    method: Literal["html", "api"] = "html"


class OutputCPOSGTJSP(OutputCnjConsultaBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJSPScraper.cposg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
