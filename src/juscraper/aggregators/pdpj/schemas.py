"""Pydantic schemas para o agregador PDPJ.

Documentam a API publica de :class:`PdpjScraper`. A API REST do PDPJ
(``api-processo-integracao.data-lake.pdpj.jus.br/processo-api``) e rica
em filtros para o endpoint de busca profunda; aqui registramos cada um
com seu nome canonico em snake_case (mapeado para o nome camelCase da
querystring no :mod:`download`).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


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


class InputPesquisaPdpj(BaseModel):
    """Filtros aceitos por :meth:`PdpjScraper.pesquisa`.

    Cobre os parametros documentados em ``GET /api/v1/processos`` (busca
    profunda). O client converte cada nome canonico em snake_case para o
    parametro camelCase da API antes de enviar a requisicao.
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
    fase: str | None = None
    situacao_atual: str | None = None
    segmento_justica: str | None = None
    tribunal: str | None = None
    tipo_operacao: str | None = None
    numero_historico: str | None = None
    data_atualizacao_inicio: str | None = None
    data_atualizacao_fim: str | None = None
    data_primeiro_ajuizamento_inicio: str | None = None
    data_primeiro_ajuizamento_fim: str | None = None
    campo_ordenacao: str | None = None
    paginas: int | list[int] | range | None = None
    itens_por_pagina: int = 100

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class InputContarPdpj(BaseModel):
    """Filtros aceitos por :meth:`PdpjScraper.contar`.

    O endpoint ``/processos:contar`` aceita o mesmo conjunto de filtros
    do ``/processos`` exceto os campos de paginacao/ordenacao
    (``campoOrdenacao``, ``searchAfter``, ``id``).
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


class InputDownloadDocumentsPdpj(BaseModel):
    """Input aceito por :meth:`PdpjScraper.download_documents`.

    ``base_df`` e tipado como ``Any`` porque pydantic nao tem validador
    nativo para ``pandas.DataFrame``. ``with_text``/``with_binary``
    selecionam quais conteudos baixar — pelo menos um deve ser ``True``.
    """

    base_df: Any
    max_docs_per_process: int | None = None
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
