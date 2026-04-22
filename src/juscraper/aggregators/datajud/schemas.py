"""Pydantic schemas for the DataJud aggregator.

Ainda nao wired em :mod:`juscraper.aggregators.datajud.client` — este
arquivo e documentacao executavel da API publica ate o agregador ser
refatorado para o pipeline canonico da #93. A lista de campos bate
byte-a-byte com a assinatura publica de
:meth:`DatajudScraper.listar_processos`.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class InputListarProcessosDataJud(BaseModel):
    """Accepted input for :meth:`DatajudScraper.listar_processos`.

    A API do DataJud e baseada em Elasticsearch. A escolha do alias-indice
    acontece automaticamente a partir de ``tribunal`` (sigla) ou dos
    digitos identificadores do ``numero_processo`` (CNJ). Quando nenhum
    dos dois e fornecido, o client atual levanta ``ValueError`` em vez de
    consultar tudo.

    ``paginas`` e tipado como ``range`` porque a API usa
    ``search_after`` para paginacao profunda; o client corre a cada pagina
    ate atingir ``paginas.stop`` ou o fim dos resultados.
    """

    numero_processo: str | list[str] | None = None
    tribunal: str | None = None
    ano_ajuizamento: int | None = None
    classe: str | None = None
    assuntos: list[str] | None = None
    mostrar_movs: bool = False
    paginas: range | None = None
    tamanho_pagina: int = 1000

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
    resto do payload sem precisar enumerar campo a campo.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """

    numeroProcesso: str

    model_config = ConfigDict(extra="allow")
