"""Pydantic schemas for TJES scraper endpoints.

Wired em :mod:`juscraper.courts.tjes.client` desde o lote L1 do #165 —
:meth:`TJESScraper.cjsg_download` e :meth:`TJESScraper.cjpg_download`
validam kwargs via :class:`InputCJSGTJES` / :class:`InputCJPGTJES` com
``extra="forbid"`` herdado de :class:`SearchBase`.
"""
from __future__ import annotations

from datetime import date
from typing import ClassVar, Literal

from pydantic import model_validator

from ...schemas import (
    DataJulgamentoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
    TamanhoPagina,
)

# Opcoes do seletor "Ordenacao" do portal para cada core, capturadas em
# 15/11/2026 de ``assets/ConsultasPublicas-*.js``. Fora delas, a API responde
# HTTP 500 (campo inexistente no core) ou aceita sem ordenar (campo vazio no core).
_ORDENACAO_PJE = ("dt_juntada desc", "dt_juntada asc", "nr_processo asc", "nr_processo desc")
ORDENACOES_POR_CORE: dict[str, tuple[str, ...]] = {
    "pje1g": _ORDENACAO_PJE,
    "pje2g": _ORDENACAO_PJE,
    "pje2g_mono": _ORDENACAO_PJE,
    "legado": (
        "data_julgamento desc",
        "data_julgamento asc",
        "data_publicacao desc",
        "data_publicacao asc",
        "numero_processo_legado asc",
        "numero_processo_legado desc",
    ),
    "turma_recursal_legado": (
        "data_julgamento desc",
        "data_julgamento asc",
        "num_processo asc",
        "num_processo desc",
    ),
}

OrdenacaoCJSG = Literal[
    "dt_juntada desc",
    "dt_juntada asc",
    "nr_processo asc",
    "nr_processo desc",
    "data_julgamento desc",
    "data_julgamento asc",
    "data_publicacao desc",
    "data_publicacao asc",
    "numero_processo_legado asc",
    "numero_processo_legado desc",
    "num_processo asc",
    "num_processo desc",
]
OrdenacaoCJPG = Literal["dt_juntada desc", "dt_juntada asc", "nr_processo asc", "nr_processo desc"]


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

    ``ordenacao`` aceita as opcoes do seletor "Ordenacao" do portal, que
    dependem do ``core`` (:data:`ORDENACOES_POR_CORE`); ``None`` ordena por
    relevancia.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    core: Literal["pje2g", "pje2g_mono", "legado", "turma_recursal_legado"] = "pje2g"
    busca_exata: bool = False
    relator: str | None = None
    orgao_julgador: str | None = None
    classe: str | None = None
    jurisdicao: str | None = None
    assunto: str | None = None
    ordenacao: OrdenacaoCJSG | None = None
    tamanho_pagina: TamanhoPagina = 20

    @model_validator(mode="after")
    def _ordenacao_do_core(self) -> InputCJSGTJES:
        aceitas = ORDENACOES_POR_CORE[self.core]
        if self.ordenacao is not None and self.ordenacao not in aceitas:
            raise ValueError(
                f"ordenacao={self.ordenacao!r} nao existe no core {self.core!r}. "
                f"Use uma de: {', '.join(aceitas)}."
            )
        return self


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


class OutputCJSGTJES(_OutputCJSGTJESBase, OutputDataPublicacaoMixin):
    """Output do cjsg (2o grau) do TJES.

    Nos cores ``legado`` e ``turma_recursal_legado`` nao ha ``dt_juntada``:
    a data vem em ``data_julgamento``, e o ``legado`` traz tambem
    ``data_publicacao``. As demais colunas canonicas vem dos campos proprios
    de cada core (ver ``tjes.parse._CAMPOS_POR_CORE_LEGADO``).
    """


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
    # Opcoes do core ``pje1g`` (ver ORDENACOES_POR_CORE).
    ordenacao: OrdenacaoCJPG | None = None
    tamanho_pagina: TamanhoPagina = 20


class OutputCJPGTJES(_OutputCJSGTJESBase):
    """Output do cjpg (1o grau) do TJES. Mesmas colunas do cjsg — so muda o core."""
