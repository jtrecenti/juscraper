"""Parser dos envelopes JSON da consulta pública do PJe do TRF3.

Recebe o dicionário bruto montado por
:func:`juscraper.courts.trf3.download.baixar_processo` e devolve um registro
plano com as colunas que o ``cpopg`` do TRF3 entregava quando o portal era
JSF (``processo``, ``classe``, ``assunto``, ``data_distribuicao``,
``orgao_julgador``, ``jurisdicao``, ``endereco_orgao``, ``polo_ativo``,
``polo_passivo``, ``movimentacoes``, ``documentos``), mais as que a API passou
a expor (``orgao_julgador_colegiado``, ``outros_interessados``). O mesmo
parser serve ao 1º e ao 2º grau.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# Chave da API -> chave de saída de cada parte. ``procuradoriaDomicilio`` fica
# de fora porque só repete se a procuradoria recebe intimação no domicílio
# eletrônico, sem uso para a consulta.
_CAMPOS_PARTE = {
    "participante": "participante",
    "nome": "nome",
    "tipo": "tipo",
    "situacao": "situacao",
    "principal": "principal",
    "procuradoria": "procuradoria",
    "segredoJustica": "segredo_justica",
}

# Prefixo de data na descrição dos documentos: "22/09/2026 13:33:36 - SENTENÇA (SENTENÇA)".
_DOC_DESCRICAO_RE = re.compile(r"^(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\s+-\s+(.+)$", re.DOTALL)


def _texto(valor: Any) -> str | None:
    """Tira espaços das pontas de cada linha e troca string vazia por ``None``.

    A API usa ``""`` para campo ausente. Processos com mais de um assunto
    trazem um por linha, com espaço antes da quebra; a quebra fica.
    """
    if valor is None:
        return None
    texto = "\n".join(linha.strip() for linha in str(valor).strip().splitlines())
    return texto or None


def _data_br(valor: Any) -> str | None:
    """Converte ``2025-09-24T15:10:17.231`` em ``24/09/2025``.

    O portal JSF exibia só a data da distribuição, em ``DD/MM/AAAA``; manter o
    formato preserva a coluna para quem já a consumia. Valor que não casa com
    ISO volta como veio.
    """
    texto = _texto(valor)
    if texto is None:
        return None
    try:
        return datetime.fromisoformat(texto).strftime("%d/%m/%Y")
    except ValueError:
        return texto


def _itens(paginas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Concatena o ``result`` de todas as páginas de um recurso."""
    itens: list[dict[str, Any]] = []
    for pagina in paginas:
        itens.extend(pagina.get("result") or [])
    return itens


def _parse_partes(paginas: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if paginas is None:
        return None
    return [{saida: item.get(chave) for chave, saida in _CAMPOS_PARTE.items()} for item in _itens(paginas)]


def _parse_movimentacoes(paginas: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Lista ``[{data, descricao, documento}]``, na ordem da API (mais recente primeiro)."""
    if paginas is None:
        return None
    return [
        {
            "data": _texto(item.get("dataAtualizacao")),
            "descricao": _texto(item.get("movimento")),
            "documento": _texto(item.get("documento")),
        }
        for item in _itens(paginas)
    ]


def _parse_documentos(paginas: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Lista ``[{id, data, descricao, binario}]``.

    ``id`` é o token que :func:`juscraper.courts.trf3.download.baixar_documento`
    usa para baixar o PDF. A data vem embutida no início da descrição; quando
    o formato não casa, a descrição inteira fica em ``descricao`` e ``data``
    sai ``None``.
    """
    if paginas is None:
        return None
    documentos: list[dict[str, Any]] = []
    for item in _itens(paginas):
        descricao = _texto(item.get("descricao"))
        data = None
        if descricao:
            m = _DOC_DESCRICAO_RE.match(descricao)
            if m:
                data, descricao = m.group(1), m.group(2).strip()
        documentos.append(
            {
                "id": item.get("id"),
                "data": data,
                "descricao": descricao,
                "binario": item.get("binario"),
            }
        )
    return documentos


def parse_processo(bruto: dict[str, Any]) -> dict[str, Any]:
    """Transforma o dicionário bruto de um processo num registro plano.

    Recurso sem itens vira lista vazia; recurso que não pôde ser baixado
    (``None`` no bruto, ver :func:`juscraper.courts.trf3.download.baixar_processo`)
    vira ``None``, para distinguir "não há partes" de "a API falhou".
    """
    dados = (bruto.get("dados") or {}).get("result") or {}
    return {
        "processo": _texto(dados.get("numeroProcesso")),
        "classe": _texto(dados.get("classeJudicial")),
        "assunto": _texto(dados.get("assunto")),
        "data_distribuicao": _data_br(dados.get("dataDistribuicao")),
        "orgao_julgador": _texto(dados.get("orgaoJulgador")),
        "orgao_julgador_colegiado": _texto(dados.get("orgaoJulgadorColegiado")),
        "jurisdicao": _texto(dados.get("jurisdicao")),
        "endereco_orgao": _texto(dados.get("endereco")),
        "polo_ativo": _parse_partes(bruto.get("poloAtivo")),
        "polo_passivo": _parse_partes(bruto.get("poloPassivo")),
        "outros_interessados": _parse_partes(bruto.get("outrosInteressados")),
        "movimentacoes": _parse_movimentacoes(bruto.get("movimentacoes")),
        "documentos": _parse_documentos(bruto.get("documentos")),
    }
