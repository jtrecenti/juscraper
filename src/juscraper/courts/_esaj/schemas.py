"""Schemas pydantic do eSAJ: ``cjsg`` (TJAC/TJAL/TJAM/TJCE/TJMS) e ``cjpg`` (TJSP/TJMS).

O ``cjsg`` do TJSP diverge (``baixar_sg`` em vez de ``origem``, sem
``numero_recurso``/``data_publicacao_*``) e tem schema próprio em
``juscraper.courts.tjsp.schemas``. Os schemas do ``cjpg`` servem a todo
tribunal construído sobre :class:`~juscraper.courts._esaj.cjpg.EsajCjpgScraper`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ...schemas import (
    AutoChunkMixin,
    CountOnlyMixin,
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    IdFiltro,
    IdFiltroUnico,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)
from ...schemas.cjsg import OutputCJSGBase


class InputCJSGEsajPuro(
    SearchBase, DataJulgamentoMixin, DataPublicacaoMixin, AutoChunkMixin, CountOnlyMixin,
):
    """Accepted input for TJAC/TJAL/TJAM/TJCE/TJMS ``cjsg``.

    Inherits ``extra='forbid'`` from :class:`SearchBase`, so unknown keyword
    arguments raise ``ValidationError`` instead of being silently ignored.
    Herda tambem os filtros de data de julgamento e de publicacao via
    :class:`DataJulgamentoMixin` / :class:`DataPublicacaoMixin`.

    ``classe``/``assunto``/``orgao_julgador`` aceitam ``int``, ``str`` ou
    ``list[int | str]`` via :data:`IdFiltro` (refs #232). ``comarca`` aceita
    ``int`` ou ``str`` (single-value, backend ``cdComarca``).
    """

    ementa: str | None = None
    numero_recurso: str | None = None
    classe: IdFiltro = None
    assunto: IdFiltro = None
    comarca: IdFiltroUnico = None
    orgao_julgador: IdFiltro = None
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


class InputCJPGEsaj(SearchBase, DataJulgamentoMixin, AutoChunkMixin, CountOnlyMixin):
    """Entrada aceita pelo ``cjpg`` do eSAJ (TJSP e TJMS); kwarg desconhecido falha por ``extra='forbid'``.

    Sobrescreve ``pesquisa`` com default vazio porque o eSAJ permite buscar
    so por filtros (ex.: ``classe=[417]``) sem termo textual.

    ``classe``/``assunto``/``vara`` aceitam ``int``, ``str`` ou
    ``list[int | str]`` via :data:`IdFiltro` (refs #232). Nomes canonicos
    seguem o singular do projeto; os plurais ``classes``/``assuntos``/``varas``
    sao alias deprecados popados no client (:meth:`~juscraper.courts._esaj.cjpg.EsajCjpgScraper.cjpg_download`)
    com :class:`DeprecationWarning`.
    """

    pesquisa: str = ""
    classe: IdFiltro = None
    assunto: IdFiltro = None
    vara: IdFiltro = None
    id_processo: str | None = None


class OutputCJPGEsaj(BaseModel):
    """Colunas observaveis numa linha do DataFrame do ``cjpg`` do eSAJ (TJSP e TJMS).

    Reflete :mod:`juscraper.courts._esaj.cjpg_parse`. Diferente do ``cjsg``,
    ``cjpg`` nao entrega ementa nem ``processo`` formatado em CNJ — so o par
    de IDs internos (``id_processo`` / ``cd_processo``) que permitem seguir
    para a consulta de 1o grau.
    """

    id_processo: str
    cd_processo: str | None = None
    cd_foro: str | None = None
    nm_alias: str | None = None
    cd_documento: str | None = None

    model_config = ConfigDict(extra="allow")
