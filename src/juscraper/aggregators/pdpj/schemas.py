"""Pydantic schemas para o agregador PDPJ.

Documentam a API publica de :class:`PdpjScraper`. A API REST do PDPJ
(``api-processo-integracao.data-lake.pdpj.jus.br/processo-api``) e rica
em filtros para o endpoint de busca profunda; aqui registramos cada um
com seu nome canonico em snake_case (mapeado para o nome camelCase da
querystring no :mod:`download`).
"""
from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from ...schemas import TamanhoPagina
from .._pdpj_sso.schemas import InputAuthGovbrBase


class InputAuthPdpj(BaseModel):
    """Input aceito por :meth:`PdpjScraper.auth`.

    Recebe o JWT obtido fora da biblioteca (devtools do PDPJ logado, ou
    fluxo OAuth proprio). O client decodifica sem verificar assinatura
    apenas para validar o formato e detectar tokens expirados.
    """

    token: str

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class InputAuthGovbrPdpj(InputAuthGovbrBase):
    """Input aceito por :meth:`PdpjScraper.auth_govbr`; campos em :class:`InputAuthGovbrBase`."""


class InputCnjPdpj(BaseModel):
    """Input minimo de endpoints que recebem um (ou varios) numero(s) CNJ.

    Usado por :meth:`PdpjScraper.existe`, :meth:`PdpjScraper.cpopg`,
    :meth:`PdpjScraper.documentos`, :meth:`PdpjScraper.movimentos` e
    :meth:`PdpjScraper.partes`. ``id_cnj`` aceita ``str`` ou ``list[str]``
    — o client itera quando recebe lista.
    """

    id_cnj: str | list[str]

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class _InputFiltrosPdpj(BaseModel):
    """Filtros comuns a :meth:`PdpjScraper.pesquisa` e :meth:`PdpjScraper.contar`.

    Cada nome canonico em snake_case vira o parametro camelCase da API
    (``_QUERY_PARAM_MAP`` em :mod:`juscraper.aggregators.pdpj.client`).
    """

    numero_processo: str | None = None
    numero_processo_sintetico: str | None = None
    id: str | None = None
    id_fonte_dados_codex: str | None = None
    cpf_cnpj_parte: str | None = None
    nome_parte: str | None = None
    outro_nome_parte: str | None = None
    polo_parte: str | None = None
    situacao_parte: str | None = None
    nome_representante: str | None = None
    oab_representante: str | None = None
    href: str | None = None
    id_assunto_judicial: str | None = None
    id_classe: str | None = None
    id_orgao_julgador: str | list[str] | None = None
    instancia: str | None = None
    segmento_justica: str | None = None
    tribunal: str | None = None
    numero_historico: str | None = None
    data_atualizacao_inicio: str | None = None
    data_atualizacao_fim: str | None = None
    data_primeiro_ajuizamento_inicio: str | None = None
    data_primeiro_ajuizamento_fim: str | None = None

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class InputPesquisaPdpj(_InputFiltrosPdpj):
    """Filtros aceitos por :meth:`PdpjScraper.pesquisa`.

    Cobre os parametros documentados em ``GET /api/v1/processos`` (busca
    profunda).
    """

    fase: str | None = None
    situacao_atual: str | None = None
    tipo_operacao: str | None = None
    campo_ordenacao: str | None = None
    paginas: int | list[int] | range | None = None
    itens_por_pagina: TamanhoPagina = 100


class InputContarPdpj(_InputFiltrosPdpj):
    """Filtros aceitos por :meth:`PdpjScraper.contar`.

    Endpoint ``/processos:contar``, sem ordenacao nem paginacao.
    """
    # ``fase``, ``situacao_atual`` e ``tipo_operacao`` ficam de fora: a
    # especificacao publica da API (``processo-api/v2/api-docs``, Swagger
    # v1.7.36, conferida em 27/11/2026) os declara em ``GET /api/v1/processos``
    # e nao em ``/processos:contar``. Aceita-los arriscaria um total sem filtro.


class InputDownloadDocumentsPdpj(BaseModel):
    """Input aceito por :meth:`PdpjScraper.download_documents`.

    ``base_df`` aceita somente :class:`pandas.DataFrame`. ``with_text`` e
    ``with_binary`` são coeridos para ``bool``. ``max_docs_per_process``
    aceita ``None`` ou inteiro não negativo; valor negativo levanta
    ``ValidationError``.

    O significado do limite (o que ocupa vaga, o que o zero faz) e o
    tratamento das falhas de download estão em
    :meth:`PdpjScraper.download_documents`.
    """

    base_df: pd.DataFrame
    max_docs_per_process: int | None = Field(default=None, ge=0)
    with_text: bool = True
    with_binary: bool = False

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class OutputCpopgPdpj(BaseModel):
    """Colunas garantidas em :meth:`PdpjScraper.cpopg`.

    Cada CNJ pode gerar mais de uma linha quando a API retorna lista
    com varias tramitacoes (raro mas suportado).
    """

    processo: str
    numero_processo: str | None = None

    model_config = ConfigDict(extra="allow")


class OutputDocumentosPdpj(BaseModel):
    """Colunas garantidas em :meth:`PdpjScraper.documentos`."""

    processo: str
    id_documento: str | None = None

    model_config = ConfigDict(extra="allow")


class OutputMovimentosPdpj(BaseModel):
    """Colunas garantidas em :meth:`PdpjScraper.movimentos`."""

    processo: str

    model_config = ConfigDict(extra="allow")


class OutputPartesPdpj(BaseModel):
    """Colunas garantidas em :meth:`PdpjScraper.partes`."""

    processo: str

    model_config = ConfigDict(extra="allow")


class OutputPesquisaPdpj(BaseModel):
    """Colunas garantidas em :meth:`PdpjScraper.pesquisa`."""

    numero_processo: str | None = None

    model_config = ConfigDict(extra="allow")


class OutputDownloadDocumentsPdpj(BaseModel):
    """Colunas garantidas em :meth:`PdpjScraper.download_documents`.

    Cada linha representa um documento. ``processo`` liga de volta ao
    DataFrame original; ``texto`` e ``binario`` carregam o conteudo
    quando solicitado.
    """

    processo: str
    id_documento: str | None = None

    model_config = ConfigDict(extra="allow")
