"""Pydantic schemas for TJRS scraper endpoints.

Wired em :mod:`juscraper.courts.tjrs.client` desde o lote L3 do #165 —
:meth:`TJRSScraper.cjsg_download` valida kwargs via :class:`InputCJSGTJRS`
com ``extra="forbid"`` herdado de :class:`SearchBase`.
"""
from __future__ import annotations

from typing import ClassVar

from ...schemas import (
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)


class InputCJSGTJRS(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJRS ``cjsg`` / ``cjsg_download``.

    Endpoint GSA (Google Search Appliance) com paginacao por offset.
    ``pesquisa`` aceita os aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Apos a normalizacao, os kwargs que sobram caem aqui e
    sao rejeitados por ``extra="forbid"`` herdado de :class:`SearchBase`.
    Filtros de data herdados dos mixins. O parametro ``session`` do
    metodo publico nao aparece aqui (dependencia de runtime, nao da API).
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    classe: str | None = None
    assunto: str | None = None
    orgao_julgador: str | None = None
    relator: str | None = None
    tipo_processo: str | None = None
    secao: str | None = None


class OutputCJSGTJRS(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRSScraper.cjsg`.

    Reflete ``tjrs.parse.cjsg_parse_manager`` apos renomeacao canonica
    (``classe_cnj`` -> ``classe``, ``assunto_cnj`` -> ``assunto``). O
    backend GSA (Google Search Appliance) retorna muitos campos auxiliares
    (``cod_*``) que chegam via ``extra='allow'``.
    """

    classe: str | None = None
    assunto: str | None = None
    tribunal: str | None = None
    tipo_processo: str | None = None
    url: str | None = None
    documento_text: str | None = None
    documento_tiff: str | None = None
    ementa_text: str | None = None
    mes_ano_publicacao: str | None = None
    origem: str | None = None
    secao: str | None = None
    ano_julgamento: str | int | None = None
    nome_relator: str | None = None
    ind_segredo_justica: str | bool | None = None
    ementa_referencia: str | None = None
    tipo_documento: str | None = None
    dthr_criacao: str | None = None
