"""Schemas pydantic do eSAJ: ``cjsg`` (TJAC/TJAL/TJAM/TJCE/TJMS) e ``cjpg`` (TJSP/TJMS).

O ``cjsg`` do TJSP diverge (``baixar_sg`` em vez de ``origem``, sem
``data_publicacao_*``) e tem schema próprio em
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


class InputCJSGEsajBase(SearchBase, DataJulgamentoMixin, AutoChunkMixin, CountOnlyMixin):
    """Campos do ``cjsg`` que a base eSAJ le em todo tribunal.

    Tipo de :attr:`~juscraper.courts._esaj.base.EsajSearchScraper.INPUT_CJSG`:
    o schema de cada tribunal herda daqui, e o codigo compartilhado le
    ``data_julgamento_*``, ``auto_chunk``, ``tipo_decisao``, ``paginas`` e
    os filtros do formulario sem depender do schema concreto.

    ``classe``/``assunto``/``orgao_julgador`` aceitam ``int``, ``str`` ou
    ``list[int | str]`` via :data:`IdFiltro` (refs #232). ``comarca`` aceita
    ``int`` ou ``str`` (single-value, backend ``cdComarca``). Depois da
    validacao, os quatro sao ``str | None``.
    """

    tipo_decisao: Literal["acordao", "monocratica"] = "acordao"
    ementa: str | None = None
    numero_recurso: str | None = None
    classe: IdFiltro = None
    assunto: IdFiltro = None
    comarca: IdFiltroUnico = None
    orgao_julgador: IdFiltro = None


class InputCJSGEsajPuro(InputCJSGEsajBase, DataPublicacaoMixin):
    """Accepted input for TJAC/TJAL/TJAM/TJCE/TJMS ``cjsg``.

    Inherits ``extra='forbid'`` from :class:`SearchBase`, so unknown keyword
    arguments raise ``ValidationError`` instead of being silently ignored.
    Herda tambem os filtros de data de julgamento e de publicacao via
    :class:`DataJulgamentoMixin` / :class:`DataPublicacaoMixin`, e os
    filtros do formulario (``classe``, ``comarca`` etc.) via
    :class:`InputCJSGEsajBase`.
    """

    origem: Literal["T", "R"] = "T"


class OutputCJSGEsaj(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Columns observable in eSAJ cjsg DataFrames.

    Minimum: ``processo``, ``ementa`` (inherited from :class:`OutputCJSGBase`).
    ``relator`` / ``orgao_julgador`` via :class:`OutputRelatoriaMixin`;
    ``data_publicacao`` via :class:`OutputDataPublicacaoMixin` (eSAJ
    entrega a data quando esta presente). ``extra='allow'`` is inherited
    so tribunal-specific extras (e.g., ``classe_assunto``) don't break
    validation.

    O rótulo HTML ``"Relator(a):"`` vira a coluna canônica ``relator``.
    """

    cd_acordao: str | None = None
    cd_foro: str | None = None
    # Rótulos do HTML de resultado: "Classe/Assunto:", "Comarca:" e, em
    # algumas páginas do TJMS, "Classe:" sozinho.
    classe_assunto: str | None = None
    classe: str | None = None
    comarca: str | None = None


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

    O juiz que proferiu a decisao (rotulo ``"Magistrado:"`` na pagina) sai em
    ``relator``, o nome canonico do ``cjsg``. O campo e declarado aqui, e nao
    herdado de ``OutputRelatoriaMixin``, porque o mixin traz tambem
    ``orgao_julgador``, que o ``cjpg`` nao tem.
    """

    id_processo: str
    # Rótulos da tabela de cada processo, como saem de ``_extrair_dados_processo``.
    classe: str | None = None
    assunto: str | None = None
    comarca: str | None = None
    foro: str | None = None
    vara: str | None = None
    data_disponibilizacao: str | None = None
    decisao: str | None = None
    cd_processo: str | None = None
    cd_foro: str | None = None
    nm_alias: str | None = None
    cd_documento: str | None = None
    relator: str | None = None

    model_config = ConfigDict(extra="allow")
