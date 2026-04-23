"""Pydantic schemas for eSAJ cjsg (TJAC/TJAL/TJAM/TJCE/TJMS).

TJSP has a divergent public API (``baixar_sg`` vs ``origem``, missing
``numero_recurso``/``data_publicacao_*``) and gets its own schema in
``juscraper.courts.tjsp.schemas``.
"""
from __future__ import annotations

from typing import Literal

from ...schemas import (
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)
from ...schemas.cjsg import OutputCJSGBase


class InputCJSGEsajPuro(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJAC/TJAL/TJAM/TJCE/TJMS ``cjsg``.

    Inherits ``extra='forbid'`` from :class:`SearchBase`, so unknown keyword
    arguments raise ``ValidationError`` instead of being silently ignored.
    Herda tambem os filtros de data de julgamento e de publicacao via
    :class:`DataJulgamentoMixin` / :class:`DataPublicacaoMixin`.
    """

    ementa: str | None = None
    numero_recurso: str | None = None
    classe: str | None = None
    assunto: str | None = None
    comarca: str | None = None
    orgao_julgador: str | None = None
    origem: Literal["T", "R"] = "T"
    tipo_decisao: Literal["acordao", "monocratica"] = "acordao"


class OutputCJSGEsaj(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Columns observable in eSAJ cjsg DataFrames.

    Minimum: ``processo``, ``ementa`` (inherited from :class:`OutputCJSGBase`).
    ``relator`` / ``orgao_julgador`` via :class:`OutputRelatoriaMixin`;
    ``data_publicacao`` via :class:`OutputDataPublicacaoMixin` (eSAJ
    entrega a data quando esta presente). ``extra='allow'`` is inherited
    so tribunal-specific extras (e.g., ``classe_assunto``) don't break
    validation.

    TODO (revisar com calma em PR dedicado): o parser eSAJ em
    :func:`juscraper.courts._esaj.parse._normalize_key` transforma a label
    HTML ``"Relator(a):"`` em chave ``relatora`` (remove ``(`` e ``)``,
    colando o sufixo ``a`` do desdobramento masculino/feminino). Resultado:
    o DataFrame emitido tem coluna ``relatora``, nao ``relator`` — a mesma
    divergencia canonica que o PR #117 eliminou em TJES/TJRN/TJRS/TJPE/
    TJRO/TJMT. ``relatora`` abaixo e explicito para manter o Output honesto
    sobre o que o parser hoje entrega; o ``relator`` herdado do mixin e
    o contrato canonico forward-looking. A correcao estrutural e
    normalizar ``relatora -> relator`` em ``_normalize_key`` (e remover
    este campo), o que e breaking para quem usa ``df["relatora"]`` em
    6 tribunais eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP). Deve ser feito em
    PR proprio com entrada no CHANGELOG na mesma tabela de "nomes
    canonicos de coluna", sem misturar com o escopo do #117.
    """

    cd_acordao: str | None = None
    cd_foro: str | None = None
    # Ver TODO no docstring — ``relatora`` e o nome real que o parser emite
    # hoje; canonico ``relator`` ja vem do OutputRelatoriaMixin e sera
    # unificado em PR dedicado.
    relatora: str | None = None
