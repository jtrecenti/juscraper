"""Pydantic schemas for the DataJud aggregator.

Wired em :mod:`juscraper.aggregators.datajud.client` via o atributo de
classe ``DatajudScraper.INPUT_LISTAR_PROCESSOS``. Kwargs desconhecidos
em :meth:`DatajudScraper.listar_processos` viram ``TypeError`` traduzido
por :func:`juscraper.utils.params.raise_on_extra_kwargs`. A lista de
campos bate byte-a-byte com a assinatura publica do metodo.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...schemas import PaginasMixin
from .mappings import TIPOS_MOVIMENTACAO

# Campos do schema que sao filtros amigaveis e constroem partes da query
# Elasticsearch internamente. Quando ``query`` (override total) e fornecido,
# nenhum desses pode coexistir — o validator gera ``ValidationError`` listando
# exatamente quais foram passados junto. ``tribunal`` fica de fora porque ele
# nao entra na query, e sim no path do alias-indice.
_FILTROS_AMIGAVEIS = (
    "numero_processo",
    "ano_ajuizamento",
    "classe",
    "assuntos",
    "data_ajuizamento_inicio",
    "data_ajuizamento_fim",
    "tipos_movimentacao",
    "movimentos_codigo",
    "orgao_julgador",
)


class InputListarProcessosDataJud(PaginasMixin):
    """Accepted input for :meth:`DatajudScraper.listar_processos`.

    A API do DataJud e baseada em Elasticsearch. A escolha do alias-indice
    acontece automaticamente a partir de ``tribunal`` (sigla) ou dos
    digitos identificadores do ``numero_processo`` (CNJ). Quando nenhum
    dos dois e fornecido, o client atual levanta ``ValueError`` em vez de
    consultar tudo.

    ``paginas`` herda o contrato de :class:`PaginasMixin`
    (``int | list[int] | range | None``). O cursor ``search_after`` da API
    e forwards-only, entao o metodo publico converte ``list`` esparsa em
    ``range(min, max+1)`` antes da iteracao — ``paginas=[3, 5]`` baixa as
    paginas 3, 4 e 5 e o usuario recebe o DataFrame agregado.

    **Filtros de data**: o DataJud filtra por ``dataAjuizamento``, nao por
    julgamento. Por isso o nome canonico aqui e ``data_ajuizamento_inicio``/
    ``_fim`` em vez do alias generico ``data_inicio``/``_fim`` (que
    ``normalize_datas`` mapeia para ``data_julgamento_*`` no mundo
    jurisprudencia). ``extra='forbid'`` faz quem usar o nome generico
    receber um erro explicito.

    **Override Elasticsearch**: ``query`` recebe um ``dict`` literal que
    vira a chave ``query`` do payload. Mutuamente exclusivo com todos os
    filtros amigaveis (refs #49). Em troca, oferece paridade com requisicao
    direta para ``/<alias>/_search``: o usuario consegue ``must_not``,
    ``should``, ``range`` em campos arbitrarios, ``wildcard``, ``nested``,
    etc., usando o shape oficial documentado em
    https://datajud-wiki.cnj.jus.br/api-publica/.
    """

    numero_processo: str | list[str] | None = None
    tribunal: str | None = None
    ano_ajuizamento: int | None = None
    classe: str | None = None
    assuntos: list[str] | None = None
    data_ajuizamento_inicio: str | None = None
    data_ajuizamento_fim: str | None = None
    tipos_movimentacao: list[str] | None = None
    movimentos_codigo: list[int] | None = None
    orgao_julgador: str | None = None
    query: dict[str, Any] | None = None
    mostrar_movs: bool = False
    # Limites do parametro ``size`` da API publica do DataJud
    # (datajud-wiki.cnj.jus.br/api-publica/exemplos/exemplo3/): a doc
    # oficial documenta 10 a 10000 hits por requisicao. Default 5000 —
    # testes empiricos mostraram que 10000 estoura ``HTTP 504`` no
    # gateway intermitentemente; 5000 e ~2.5x mais rapido que 1000 com
    # margem confortavel sob o timeout. Em caso de ``HTTP 504``/
    # ``Timeout``, ``call_datajud_api`` faz fallback automatico para
    # ``size // 4`` (minimo ``FALLBACK_MIN_SIZE``).
    tamanho_pagina: int = Field(default=5000, ge=10, le=10000)

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    @model_validator(mode="after")
    def _validar_datas_e_ano_excluem(self) -> "InputListarProcessosDataJud":
        if self.ano_ajuizamento is not None and (
            self.data_ajuizamento_inicio is not None
            or self.data_ajuizamento_fim is not None
        ):
            raise ValueError(
                "'ano_ajuizamento' e 'data_ajuizamento_inicio'/'data_ajuizamento_fim' "
                "sao mutuamente exclusivos. Use apenas um dos dois."
            )
        return self

    @model_validator(mode="after")
    def _validar_formato_datas(self) -> "InputListarProcessosDataJud":
        for campo in ("data_ajuizamento_inicio", "data_ajuizamento_fim"):
            valor = getattr(self, campo)
            if valor is None:
                continue
            try:
                date.fromisoformat(valor)
            except ValueError as exc:
                raise ValueError(
                    f"'{campo}' deve estar no formato 'YYYY-MM-DD' (ISO 8601). "
                    f"Recebido: {valor!r}."
                ) from exc
        return self

    @model_validator(mode="after")
    def _validar_range_datas(self) -> "InputListarProcessosDataJud":
        if (
            self.data_ajuizamento_inicio is not None
            and self.data_ajuizamento_fim is not None
        ):
            inicio = date.fromisoformat(self.data_ajuizamento_inicio)
            fim = date.fromisoformat(self.data_ajuizamento_fim)
            if inicio > fim:
                raise ValueError(
                    f"'data_ajuizamento_inicio' ({self.data_ajuizamento_inicio}) deve "
                    f"ser <= 'data_ajuizamento_fim' ({self.data_ajuizamento_fim})."
                )
        return self

    @model_validator(mode="after")
    def _validar_tipos_movimentacao_conhecidos(self) -> "InputListarProcessosDataJud":
        if not self.tipos_movimentacao:
            return self
        desconhecidos = [
            t for t in self.tipos_movimentacao  # pylint: disable=not-an-iterable
            if t not in TIPOS_MOVIMENTACAO
        ]
        if desconhecidos:
            validos = sorted(TIPOS_MOVIMENTACAO.keys())
            raise ValueError(
                f"'tipos_movimentacao' contem nomes nao mapeados: {desconhecidos}. "
                f"Validos: {validos}. Para codigos TPU fora do mapping, use "
                f"'movimentos_codigo' (lista de inteiros) diretamente."
            )
        return self

    @model_validator(mode="after")
    def _validar_query_exclusiva(self) -> "InputListarProcessosDataJud":
        if self.query is None:
            return self
        coexistentes = [
            campo for campo in _FILTROS_AMIGAVEIS if getattr(self, campo) is not None
        ]
        if coexistentes:
            raise ValueError(
                f"'query' (override total da query Elasticsearch) e mutuamente exclusivo "
                f"com os filtros amigaveis. Recebidos junto com 'query': {coexistentes}. "
                f"Use 'query' OU os filtros amigaveis."
            )
        return self

    @model_validator(mode="after")
    def _validar_query_exige_tribunal(self) -> "InputListarProcessosDataJud":
        if self.query is not None and self.tribunal is None:
            raise ValueError(
                "'query' (override) exige 'tribunal' explicito — nao ha "
                "'numero_processo' para inferir o alias-indice."
            )
        return self

    @model_validator(mode="after")
    def _validar_query_dict_nao_vazio(self) -> "InputListarProcessosDataJud":
        if self.query is not None and not self.query:
            raise ValueError(
                "'query' deve ser um dict nao-vazio com a query Elasticsearch (ex.: "
                "{'bool': {'must_not': [...]}}). Para 'sem filtro', omita o parametro."
            )
        return self


class InputContarProcessosDataJud(BaseModel):
    """Accepted input for :meth:`DatajudScraper.contar_processos`.

    Conta processos sem baixar nenhum documento — usado em analise de
    viabilidade. Aceita os mesmos filtros de
    :class:`InputListarProcessosDataJud` **menos** os parametros de
    paginacao (``paginas``, ``tamanho_pagina``, ``mostrar_movs``), que
    nao se aplicam a uma contagem (``size=0`` no Elasticsearch, sem
    cursor).

    A determinacao do alias-indice segue a mesma regra do
    ``listar_processos``: por ``tribunal`` (sigla) ou inferido do
    ``numero_processo`` (CNJ); ambos ausentes -> ``ValueError``.
    """

    numero_processo: str | list[str] | None = None
    tribunal: str | None = None
    ano_ajuizamento: int | None = None
    classe: str | None = None
    assuntos: list[str] | None = None

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class OutputListarProcessosDataJud(BaseModel):
    """Colunas observaveis em uma linha do DataFrame de
    :meth:`DatajudScraper.listar_processos`.

    O DataJud devolve documentos do Elasticsearch com muitos campos
    aninhados (``classe``, ``assuntos``, ``movimentos``, ...); a coluna
    minima garantida e ``numeroProcesso``. ``extra='allow'`` mantem o
    resto do payload sem precisar enumerar campo a campo — as chaves
    do Elasticsearch do CNJ sao camelCase e estaveis, entao o proprio
    ``_source`` vira o DataFrame.
    """

    numeroProcesso: str

    model_config = ConfigDict(extra="allow")
