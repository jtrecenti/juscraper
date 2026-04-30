"""Pydantic schemas for TJES scraper endpoints.

Wired em :mod:`juscraper.courts.tjes.client` desde o lote L1 do #165 —
:meth:`TJESScraper.cjsg_download` e :meth:`TJESScraper.cjpg_download`
validam kwargs via :class:`InputCJSGTJES` / :class:`InputCJPGTJES` com
``extra="forbid"`` herdado de :class:`SearchBase`.
"""
from __future__ import annotations

from datetime import date
from typing import ClassVar, Literal

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, OutputRelatoriaMixin, SearchBase


class InputCJSGTJES(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJES ``cjsg`` / ``cjsg_download``.

    Endpoint Elasticsearch (Solr) DSL. ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Apos a normalizacao, os kwargs que
    sobram caem aqui e sao rejeitados por ``extra="forbid"`` herdado de
    :class:`SearchBase`.

    Apenas filtro de ``data_julgamento_*`` — o backend Solr expoe um unico
    intervalo (``dataIni``/``dataFim``) mapeado para ``dt_juntada``. Nao ha
    filtro de data de publicacao; ``data_publicacao_*`` levanta
    ``TypeError`` em vez de ser silenciosamente descartado.

    O parametro ``core`` e restrito aos cores de segundo grau; para primeiro
    grau (``pje1g``), use :class:`InputCJPGTJES`.

    ``relator`` e ``classe`` sao os nomes canonicos; ``magistrado`` e
    ``classe_judicial`` (chaves brutas do Solr) sao aceitos com
    ``DeprecationWarning`` e resolvidos pelo client.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    core: Literal["pje2g", "pje2g_mono", "legado", "turma_recursal_legado"] = "pje2g"
    busca_exata: bool = False
    relator: str | None = None
    orgao_julgador: str | None = None
    classe: str | None = None
    jurisdicao: str | None = None
    assunto: str | None = None
    ordenacao: str | None = None
    per_page: int = 20


class _OutputCJSGTJESBase(OutputCJSGBase, OutputRelatoriaMixin):
    """Colunas compartilhadas entre ``cjsg`` e ``cjpg`` do TJES.

    Reflete ``tjes.parse.cjsg_parse`` apos renomeacoes canonicas
    (``nr_processo`` -> ``processo``, ``magistrado`` -> ``relator``,
    ``classe_judicial`` -> ``classe``, ``assunto_principal`` -> ``assunto``).
    ``dt_juntada`` (data da juntada do documento) e distinto de
    ``data_julgamento``; permanece como coluna propria.
    """

    classe: str | None = None
    classe_judicial_sigla: str | None = None
    assunto: str | None = None
    jurisdicao: str | None = None
    competencia: str | None = None
    dt_juntada: date | str | None = None
    id: str | int | None = None
    acordao: str | None = None
    lista_assunto: str | None = None
    localizacao: str | None = None
    cargo_julgador: str | None = None


class OutputCJSGTJES(_OutputCJSGTJESBase):
    """Output do cjsg (2o grau) do TJES."""


class InputCJPGTJES(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJES ``cjpg`` / ``cjpg_download``.

    Endpoint Elasticsearch (Solr) de primeiro grau — sempre usa o core
    ``pje1g``, por isso o campo ``core`` nao existe aqui. Aceita os mesmos
    filtros de :class:`InputCJSGTJES` (exceto ``core``) como kwargs.
    Apenas filtro de ``data_julgamento_*`` — mesmo motivo de
    :class:`InputCJSGTJES`.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    busca_exata: bool = False
    relator: str | None = None
    orgao_julgador: str | None = None
    classe: str | None = None
    jurisdicao: str | None = None
    assunto: str | None = None
    ordenacao: str | None = None
    per_page: int = 20


class OutputCJPGTJES(_OutputCJSGTJESBase):
    """Output do cjpg (1o grau) do TJES. Mesmas colunas do cjsg — so muda o core."""
