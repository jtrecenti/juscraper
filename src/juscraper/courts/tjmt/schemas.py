"""Schemas Pydantic dos endpoints do scraper do TJMT.

Integrado em :mod:`juscraper.courts.tjmt.client` desde o lote L2 do #165 —
:meth:`TJMTScraper.cjsg_download` valida kwargs via :class:`InputCJSGTJMT`
com ``extra="forbid"`` herdado de :class:`SearchBase`.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from ...schemas import (
    DataPublicacaoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
    TamanhoPagina,
)


class InputCJSGTJMT(SearchBase, DataPublicacaoMixin):
    """Entradas aceitas por ``cjsg`` e ``cjsg_download`` do TJMT.

    Endpoint REST JSON de produção. ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo.

    A API filtra datas só por publicação (``periodoDataDe``/``periodoDataAte``),
    e o fim do intervalo é inclusivo. Ela não filtra por data de julgamento nem
    por classe, então o modelo não declara ``data_julgamento_*`` nem
    ``classe``: passá-los levanta ``TypeError`` por ``extra="forbid"``, antes de
    qualquer requisição. Os aliases genéricos ``data_inicio``/``data_fim``
    apontam para ``data_julgamento_*`` em
    :func:`juscraper.utils.params.normalize_datas` e por isso também terminam
    em ``TypeError``, depois do ``DeprecationWarning`` do alias.

    ``relator`` e ``orgao_julgador`` recebem o nome, não o identificador
    numérico; o downloader tira acentos, junta espaços e passa a maiúsculas,
    e a API só casa o nome exato.

    ``BACKEND_DATE_FORMAT="%Y-%m-%d"`` (ISO) — o Hellsgate aceita datas em
    ``YYYY-MM-DD``, entao :func:`apply_input_pipeline_search` coage as
    datas para esse formato antes de validar (refs #173).
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    # TODO (#212): apertar com Literal[...] após captura do Hellsgate.
    tipo_consulta: str = "Acordao"
    relator: str | None = None
    orgao_julgador: str | None = None
    tipo_processo: str | None = None
    thesaurus: bool = False
    tamanho_pagina: TamanhoPagina = Field(default=10, ge=1)


class OutputCJSGTJMT(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJMTScraper.cjsg`.

    Reflete ``tjmt.parse.cjsg_parse``. ``numero_unico`` (formato antigo)
    ja foi renomeado para ``processo`` no parser.
    """

    id: int | str | None = None
    tipo: str | None = None
    observacao: str | None = None
    classe: str | None = None
    assunto: str | None = None
    tipo_acao: str | None = None
    tipo_processo: str | None = None
    redator_designado: str | None = None
    sigla_classe_feito: str | None = None
    instancia: str | None = None
    origem: str | None = None
    julgamento: str | None = None
