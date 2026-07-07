"""Pydantic schemas for the Falcao aggregator (Jurisprudencia Nacional da JT).

O sistema "Jurisprudencia Nacional" (hospedado pelo CSJT em
``https://jurisprudencia.jt.jus.br``, backend interno ``falcao``) expoe uma
busca unica sobre varias colecoes de documentos da Justica do Trabalho (TST +
os 24 TRTs). O endpoint publico ``/no-auth/pesquisa`` aceita um termo livre
(``texto``), a colecao alvo (``colecao``) e filtros opcionais.

Particularidades do backend refletidas aqui:

- **Colecao obrigatoria**: sem ``colecao`` o backend levanta ``NullPointerException``.
  Default ``"acordaos"`` (jurisprudencia de 2o grau, caso mais comum).
- **Tamanho de pagina restrito**: usuarios nao autenticados so podem pedir
  paginas de tamanho 5 ou 10. Qualquer outro valor recebe 403 do backend.
- **Datas em ISO** ``AAAA-MM-DD`` filtrando por data de juntada (``dataJuntada``);
  ``DD/MM/AAAA`` e ``date`` sao convertidos antes de submeter.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, field_validator

from ...schemas import OutputCJSGBase, SearchBase

COLECOES: tuple[str, ...] = (
    "acordaos",
    "sentencas",
    "decisoesmonocraticas",
    "precedentes",
    "recursorevista",
)
"""Colecoes aceitas pelo parametro ``colecao`` da API ``/no-auth/pesquisa``."""

ORDENACOES: tuple[str, ...] = (
    "mais_relevante",
    "mais_recente",
    "menos_recente",
)
"""Valores aceitos pelo parametro ``ordenacao`` (default do backend: relevancia)."""

TAMANHOS_PERMITIDOS: tuple[int, ...] = (5, 10)
"""Tamanhos de pagina que o backend libera para usuario nao autenticado."""


class InputCJSGFalcao(SearchBase):
    """Filtros aceitos por :meth:`FalcaoScraper.cjsg`.

    Herda ``pesquisa`` (obrigatorio) e ``paginas`` de :class:`SearchBase`
    (``extra="forbid"``). Cada filtro corresponde a um parametro da
    querystring do endpoint ``/no-auth/pesquisa`` — o nome canonico do
    juscraper (``relator``, ``classe``, ...) e traduzido para o nome do
    backend (``nomeRelator``, ``classeProcesso``, ...) em
    :func:`juscraper.aggregators.falcao.download.build_pesquisa_params`.

    Campos:
        colecao: Colecao alvo. Um de :data:`COLECOES`. Default ``"acordaos"``.
        tamanho_pagina: Documentos por pagina. So ``5`` ou ``10`` para
            usuario nao autenticado (:data:`TAMANHOS_PERMITIDOS`). Default 10.
        tribunais: Sigla(s) de tribunal (``"TST"``, ``"TRT3"``, ...). Backend:
            ``tribunais`` (CSV).
        relator: Nome(s) de relator. Backend: ``nomeRelator`` (CSV).
        orgao_julgador: Orgao(s) julgador(es). Backend: ``orgaoJulgador`` (CSV).
        classe: Classe(s) processual(is). Backend: ``classeProcesso`` (CSV).
        fase_processual: Fase(s) processual(is). Backend: ``faseProcessual`` (CSV).
        prioridade: Marcador(es) de prioridade. Backend: ``prioridade`` (CSV).
        tem_ementa: Restringe a documentos com/sem ementa. Backend: ``temEmenta``.
        somente_ementa: Busca ``texto`` apenas nas ementas. Backend:
            ``pesquisaSomenteNasEmentas``.
        ordenacao: Ordem dos resultados. Um de :data:`ORDENACOES`. Backend:
            ``ordenacao``. Default ``None`` (relevancia).
        data_juntada_inicio: Limite inferior de ``dataJuntada`` (ISO
            ``AAAA-MM-DD``). Backend: ``dataInicio``. Opcional.
        data_juntada_fim: Limite superior de ``dataJuntada`` (ISO
            ``AAAA-MM-DD``). Backend: ``dataFim``. Opcional.

    Os nomes ``data_juntada_*`` sao explicitos de proposito: o backend filtra
    por data de juntada do documento (nao julgamento nem publicacao), entao
    reusar ``data_julgamento_*``/``data_publicacao_*`` ou o alias generico
    ``data_inicio/fim`` (que ``normalize_datas`` mapeia para julgamento)
    induziria o usuario a erro. Mesmo racional da excecao do
    ``DatajudScraper`` (``data_ajuizamento_*``).
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    colecao: str = "acordaos"
    tamanho_pagina: int = 10
    tribunais: str | list[str] | None = None
    relator: str | list[str] | None = None
    orgao_julgador: str | list[str] | None = None
    classe: str | list[str] | None = None
    fase_processual: str | list[str] | None = None
    prioridade: str | list[str] | None = None
    tem_ementa: bool | None = None
    somente_ementa: bool | None = None
    ordenacao: str | None = None
    data_juntada_inicio: str | None = None
    data_juntada_fim: str | None = None

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    @field_validator("colecao")
    @classmethod
    def _validar_colecao(cls, v: str) -> str:
        if v not in COLECOES:
            raise ValueError(
                f"colecao invalida: {v!r}. Aceitas: {', '.join(COLECOES)}."
            )
        return v

    @field_validator("tamanho_pagina")
    @classmethod
    def _validar_tamanho(cls, v: int) -> int:
        if v not in TAMANHOS_PERMITIDOS:
            raise ValueError(
                "tamanho_pagina para usuario nao autenticado so aceita "
                f"{TAMANHOS_PERMITIDOS}; recebido {v!r}."
            )
        return v

    @field_validator("ordenacao")
    @classmethod
    def _validar_ordenacao(cls, v: str | None) -> str | None:
        if v is not None and v not in ORDENACOES:
            raise ValueError(
                f"ordenacao invalida: {v!r}. Aceitas: {', '.join(ORDENACOES)}."
            )
        return v


class OutputCJSGFalcao(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`FalcaoScraper.cjsg`.

    Cada colecao devolve um shape proprio (``acordaos`` traz ``textoAcordao``,
    ``sentencas`` traz ``textoSentenca``, etc.), mas o parser normaliza um
    nucleo canonico comum e propaga o restante via ``extra="allow"``.

    Colunas garantidas:
        processo: Numero CNJ do processo (``numeroProcesso``). Para a colecao
            ``precedentes`` — que nao tem processo unico — recebe o numero do
            precedente (``numero``, ex.: numero da sumula/OJ).
        colecao: Colecao de origem do documento (uma de :data:`COLECOES`).
        tribunal: Sigla do tribunal de origem (``TST``, ``TRT1``..``TRT24``).
        ementa: Ementa quando disponivel (so ``acordaos``); ``None`` nas demais.
        data_julgamento: Data de julgamento (``dataJulgamento``), quando existir.

    ``extra="allow"`` propaga os demais campos brutos da colecao
    (``textoAcordao``, ``score``, ``nomeRelator``, ``dataJuntada``, ...).
    """

    colecao: str
    tribunal: str | None = None

    model_config = ConfigDict(extra="allow")
