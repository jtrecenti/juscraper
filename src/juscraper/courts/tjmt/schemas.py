"""Schemas Pydantic dos endpoints do scraper do TJMT.

Integrado em :mod:`juscraper.courts.tjmt.client` desde o lote L2 do #165 —
:meth:`TJMTScraper.cjsg_download` valida kwargs via :class:`InputCJSGTJMT`
com ``extra="forbid"`` herdado de :class:`SearchBase`.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from ...schemas import (
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)


class InputCJSGTJMT(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Entradas aceitas por ``cjsg`` e ``cjsg_download`` do TJMT.

    Endpoint REST JSON de produção. ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Datas aceitam os aliases ``data_inicio``/``data_fim``
    via :func:`juscraper.utils.params.normalize_datas`.

    ``data_julgamento_*`` permanece na interface por compatibilidade, mas o
    backend atual filtra por publicação; o downloader rejeita esse filtro
    explicitamente. ``data_publicacao_*`` é o intervalo suportado nesta etapa.

    ``BACKEND_DATE_FORMAT="%Y-%m-%d"`` (ISO) — o Hellsgate aceita datas em
    ``YYYY-MM-DD``, entao :func:`apply_input_pipeline_search` coage as
    datas para esse formato antes de validar (refs #173).
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    # TODO (#212): apertar com Literal[...] após captura do Hellsgate.
    tipo_consulta: str = "Acordao"
    relator: str | None = None
    orgao_julgador: str | None = None
    classe: str | None = None
    tipo_processo: str | None = None
    thesaurus: bool = False
    tamanho_pagina: int = Field(default=10, ge=1)


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
