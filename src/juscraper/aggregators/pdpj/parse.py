"""Funcoes de parse para o agregador PDPJ.

A API responde com JSON ja estruturado — o trabalho deste modulo e (1)
adicionar a coluna pivot ``processo`` com o CNJ pesquisado e (2)
limpar/normalizar texto bruto de documentos.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_processo_row(
    detalhe: dict[str, Any],
    cnj_pesquisado: str,
) -> dict[str, Any]:
    """Constroi uma linha do DataFrame de :meth:`PdpjScraper.cpopg`.

    Mantem o JSON completo em ``detalhes`` para os campos auxiliares e
    extrai o que e mais usado (``numeroProcesso``, ``siglaTribunal``,
    ``segmentoJustica``, ``dataHoraAtualizacao``) para colunas top-level.
    """
    return {
        "processo": cnj_pesquisado,
        "numero_processo": detalhe.get("numeroProcesso"),
        "id": detalhe.get("id"),
        "sigla_tribunal": detalhe.get("siglaTribunal"),
        "segmento_justica": detalhe.get("segmentoJustica"),
        "nivel_sigilo": detalhe.get("nivelSigilo"),
        "data_atualizacao": detalhe.get("dataHoraAtualizacao"),
        "detalhes": detalhe,
    }


def build_documento_rows(
    json_data: dict[str, Any] | None,
    cnj_pesquisado: str,
) -> list[dict[str, Any]]:
    """Cada documento da resposta vira uma linha do DataFrame.

    A API embute a lista em ``documentos``; o restante do JSON descreve
    o processo. Achatamos os campos de ``arquivo`` (id, tipo, tamanho) e
    ``tipo`` (codigo, nome) para facilitar uso direto em pandas.
    """
    if not json_data:
        return []
    numero_processo = json_data.get("numeroProcesso")
    rows: list[dict[str, Any]] = []
    for doc in json_data.get("documentos", []) or []:
        if not isinstance(doc, dict):
            continue
        arquivo = doc.get("arquivo") or {}
        tipo = doc.get("tipo") or {}
        rows.append({
            "processo": cnj_pesquisado,
            "numero_processo": numero_processo,
            "id_documento": doc.get("id"),
            "id_codex": doc.get("idCodex"),
            "id_origem": doc.get("idOrigem"),
            "sequencia": doc.get("sequencia"),
            "data_juntada": doc.get("dataHoraJuntada"),
            "nome": doc.get("nome"),
            "nivel_sigilo": doc.get("nivelSigilo"),
            "tipo_codigo": tipo.get("codigo"),
            "tipo_nome": tipo.get("nome"),
            "arquivo_id": arquivo.get("id"),
            "arquivo_tipo": arquivo.get("tipo"),
            "arquivo_tamanho": arquivo.get("tamanho"),
            "arquivo_tamanho_texto": arquivo.get("tamanhoTexto"),
            "arquivo_paginas": arquivo.get("quantidadePaginas"),
            "_raw": doc,
        })
    return rows


def build_movimento_rows(
    json_data: dict[str, Any] | None,
    cnj_pesquisado: str,
) -> list[dict[str, Any]]:
    """Cada movimento da resposta vira uma linha do DataFrame."""
    if not json_data:
        return []
    numero_processo = json_data.get("numeroProcesso")
    rows: list[dict[str, Any]] = []
    for mov in json_data.get("movimentos", []) or []:
        if not isinstance(mov, dict):
            continue
        tipo = mov.get("tipo") or {}
        classe = mov.get("classe") or {}
        rows.append({
            "processo": cnj_pesquisado,
            "numero_processo": numero_processo,
            "sequencia": mov.get("sequencia"),
            "data_hora": mov.get("dataHora"),
            "id_codex": mov.get("idCodex"),
            "id_origem": mov.get("idOrigem"),
            "descricao": mov.get("descricao"),
            "tipo_id": tipo.get("id"),
            "tipo_nome": tipo.get("nome"),
            "tipo_hierarquia": tipo.get("hierarquia"),
            "classe_codigo": classe.get("codigo"),
            "classe_descricao": classe.get("descricao"),
            "_raw": mov,
        })
    return rows


def build_parte_rows(
    json_data: dict[str, Any] | None,
    cnj_pesquisado: str,
) -> list[dict[str, Any]]:
    """Cada parte da resposta vira uma linha do DataFrame."""
    if not json_data:
        return []
    numero_processo = json_data.get("numeroProcesso")
    rows: list[dict[str, Any]] = []
    for parte in json_data.get("partes", []) or []:
        if not isinstance(parte, dict):
            continue
        documentos = parte.get("documentosPrincipais") or []
        doc_principal = documentos[0] if documentos else {}
        rows.append({
            "processo": cnj_pesquisado,
            "numero_processo": numero_processo,
            "polo": parte.get("polo"),
            "tipo_parte": parte.get("tipoParte"),
            "situacao": parte.get("situacao"),
            "nome": parte.get("nome"),
            "tipo_pessoa": parte.get("tipoPessoa"),
            "documento_numero": doc_principal.get("numero"),
            "documento_tipo": doc_principal.get("tipo"),
            "_raw": parte,
        })
    return rows


def parse_pesquisa_response(
    json_data: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[Any] | None, int | None]:
    """Extrai (linhas, ``searchAfter``, total) do JSON de ``/processos``.

    Cada elemento de ``content`` vira uma linha bruta — o caller decide
    o shape final do DataFrame (varios cnj's na mesma chamada).
    """
    if not json_data:
        return [], None, None
    content = json_data.get("content") or []
    if not isinstance(content, list):
        content = []
    rows: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        rows.append({
            "numero_processo": item.get("numeroProcesso"),
            "id": item.get("id"),
            "sigla_tribunal": item.get("siglaTribunal"),
            "segmento_justica": item.get("segmentoJustica"),
            "data_atualizacao": item.get("dataHoraAtualizacao"),
            "data_ultimo_movimento": item.get("dataHoraUltimoMovimento"),
            "data_primeiro_ajuizamento": item.get("dataHoraPrimeiroAjuizamento"),
            "_raw": item,
        })
    search_after = json_data.get("searchAfter")
    total = json_data.get("total")
    if not isinstance(total, int):
        total = None
    return rows, search_after, total


def clean_document_text(text: str | None) -> str | None:
    """Remove caracteres de controle e normaliza espacos do texto bruto."""
    if not text:
        return None
    cleaned = text.replace("\x00", "").replace("\x1a", "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = cleaned.replace(" ", "\n").replace(" ", "\n")
    return cleaned.strip() or None
