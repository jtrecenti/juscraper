"""Pydantic schemas for the DataJud aggregator.

Wired em :mod:`juscraper.aggregators.datajud.client` via o atributo de
classe ``DatajudScraper.INPUT_LISTAR_PROCESSOS``. Kwargs desconhecidos
em :meth:`DatajudScraper.listar_processos` viram ``TypeError`` traduzido
por :func:`juscraper.utils.params.raise_on_extra_kwargs`. A lista de
campos bate byte-a-byte com a assinatura publica do metodo.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...schemas import PaginasMixin


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
    """

    numero_processo: str | list[str] | None = None
    tribunal: str | None = None
    ano_ajuizamento: int | None = None
    classe: str | None = None
    assuntos: list[str] | None = None
    mostrar_movs: bool = False
    # Limites do parametro ``size`` da API publica do DataJud
    # (datajud-wiki.cnj.jus.br/api-publica/exemplos/exemplo3/): a doc
    # "recomenda" de 10 a 10000 hits por requisicao. Default 5000 — testes
    # empiricos mostraram que 10000 estoura ``HTTP 504`` no gateway
    # intermitentemente; 5000 e ~2.5x mais rapido que 1000 com margem
    # confortavel sob o timeout. ``ge=1`` em vez de ``ge=10`` porque o
    # Elasticsearch sempre aceitou ``size>=1`` e os samples de teste
    # capturados da API real usam ``size=2``/``=5`` para forcar
    # paginacao com poucos hits — a doc declara 10 como guidance, nao cap
    # tecnico. ``le=10000`` e o cap real, observado no gateway.
    # Em caso de ``HTTP 504``/``Timeout``, ``call_datajud_api`` faz
    # fallback automatico para ``size // 4``.
    tamanho_pagina: int = Field(default=5000, ge=1, le=10000)

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
