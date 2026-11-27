"""Pydantic schemas for TJSP cjsg, cpopg and cposg.

TJSP has a divergent public API from the 5 eSAJ-puros:

- ``cjsg``: uses ``baixar_sg: bool`` instead of ``origem: Literal["T","R"]``;
  drops ``numero_recurso`` and ``data_publicacao_*``.
- ``cjpg``: schemas comuns com o TJMS, em :mod:`juscraper.courts._esaj.schemas`
  (``InputCJPGEsaj``/``OutputCJPGEsaj``); ``InputCJPGTJSP`` e
  ``OutputCJPGTJSP`` continuam aqui como aliases.
- ``cpopg`` / ``cposg``: consulta processual com ``method="html"``, o
  unico aceito (o ``"api"`` foi removido).

``cjsg`` e ``cjpg`` reforcam um limite de 120 caracteres em ``pesquisa``.
A verificacao de tamanho acontece em ``client.py`` **antes** de construir
o modelo pydantic para que o ``QueryTooLongError`` canonico propague
limpo em vez de ser embrulhado em ``pydantic.ValidationError``.
"""
from __future__ import annotations

from typing import Literal

from ...schemas import CnjInputBase, IdFiltro, IdFiltroUnico, OutputCnjConsultaBase, OutputDataPublicacaoMixin
from ...schemas.cjsg import OutputCJSGBase
from .._esaj.schemas import InputCJPGEsaj, InputCJSGEsajBase, OutputCJPGEsaj


class InputCJSGTJSP(InputCJSGEsajBase):
    """Accepted input for TJSP ``cjsg``. Unknown kwargs raise via ``extra='forbid'``.

    Herda filtro de data de julgamento via :class:`DataJulgamentoMixin`.
    TJSP **nao** suporta ``data_publicacao_*`` nem ``numero_recurso``.

    ``classe``/``assunto``/``orgao_julgador`` aceitam ``int``, ``str`` ou
    ``list[int | str]`` via :data:`IdFiltro` (refs #232). ``comarca`` aceita
    ``int`` ou ``str`` (single-value, backend ``cdComarca``).
    """

    ementa: str | None = None
    classe: IdFiltro = None
    assunto: IdFiltro = None
    comarca: IdFiltroUnico = None
    orgao_julgador: IdFiltro = None
    baixar_sg: bool = True


class OutputCJSGTJSP(OutputCJSGBase, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJSPScraper.cjsg`.

    Herda ``processo``, ``ementa`` e ``data_julgamento`` de
    :class:`OutputCJSGBase` e ``data_publicacao`` de
    :class:`OutputDataPublicacaoMixin`, e acrescenta as colunas do parser
    eSAJ compartilhado. As paginas trazem ``"Classe/Assunto:"`` num rotulo
    so.
    """

    cd_acordao: str | None = None
    cd_foro: str | None = None
    relator: str | None = None
    orgao_julgador: str | None = None
    classe_assunto: str | None = None
    comarca: str | None = None


InputCJPGTJSP = InputCJPGEsaj
OutputCJPGTJSP = OutputCJPGEsaj


class InputCPOPGTJSP(CnjInputBase):
    """Accepted input for :meth:`TJSPScraper.cpopg`.

    ``method`` aceita so ``'html'`` (eSAJ); o ``'api'`` foi removido. O
    schema documenta a assinatura publica — ele ainda nao esta wired no
    client.
    """

    method: Literal["html"] = "html"
    baixar_movimentacoes: bool = True
    download_pecas: bool = False


class OutputCPOPGTJSP(OutputCnjConsultaBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJSPScraper.cpopg`.

    ``cpopg`` retorna uma tupla de 4 DataFrames (movimentacoes, partes,
    peticoes diversas, dados basicos) — este schema captura a coluna
    minima compartilhada (``id_cnj``, herdada). Campos especificos de
    cada frame fluem via ``extra='allow'``.
    """


class InputCPOSGTJSP(CnjInputBase):
    """Accepted input for :meth:`TJSPScraper.cposg`.

    Como em ``cpopg``, ``method`` aceita so ``'html'``.
    """

    method: Literal["html"] = "html"


class OutputCPOSGTJSP(OutputCnjConsultaBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJSPScraper.cposg`.

    Como em :class:`OutputCPOPGTJSP`, retorna uma composicao de 4 frames;
    a coluna pivot ``id_cnj`` e herdada e os demais campos fluem via
    ``extra='allow'``.
    """
