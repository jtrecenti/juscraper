"""Validação das páginas do cursor ``search_after`` em ``DatajudScraper.listar_processos``.

Cada verificação que falha levanta ``ColetaParcialError`` com o diagnóstico
de alias, página e registros recebidos; ``client.py`` preenche
``erro.resultado`` com as páginas já guardadas.
"""
import logging
from typing import Any, NamedTuple, NoReturn, cast

import pandas as pd

from ...core.exceptions import ColetaParcialError

logger = logging.getLogger(__name__)


class _FimPagina(NamedTuple):
    """Contexto mínimo para diagnosticar o término de uma página."""

    alias: str
    pagina: int
    recebidos: int
    last_page: int | None


def _next_search_after(
    api_response: dict[str, Any],
    *,
    alias: str,
    effective_size: int,
) -> list[Any] | None:
    hits = api_response.get("hits", {}).get("hits", [])
    if not hits or len(hits) < effective_size:
        logger.info(
            "Last page reached for alias %s (less than %d results or no hits).",
            alias,
            effective_size,
        )
        return None
    search_after = hits[-1].get("sort")
    if not isinstance(search_after, list):
        logger.warning(
            "Sort parameters for 'search_after' not found in last hit. "
            "Cannot continue deep pagination."
        )
        return None
    return search_after


def _mensagem_falha_parcial(
    alias: str,
    pagina: int,
    recebidos: int,
    total_info: dict[str, Any] | None,
) -> str:
    """Diagnóstico da paginação interrompida, com quanto veio e quanto faltou.

    Vira a mensagem do ``ColetaParcialError``; os registros recebidos ficam
    em ``erro.resultado``.

    ``total_info`` é o ``hits.total`` da página 1, que a consulta já traz
    (``track_total_hits``); é ``None`` quando a falha foi na própria página 1.
    ``relation == "gte"`` indica total truncado pelo Elasticsearch, então o
    texto diz "pelo menos".
    """
    inicio = f"DataJud: falha ao consultar alias {alias!r} na página {pagina}."
    if total_info is None:
        return f"{inicio} Resultados parciais em erro.resultado: nenhum registro recebido."
    recebidos_txt = f"{inicio} Resultados parciais em erro.resultado: {recebidos} registro(s) recebido(s)"
    total = total_info.get("value")
    if not isinstance(total, int):
        return f"{recebidos_txt}; a consulta não informou o total encontrado."
    total_txt = str(total) if total_info.get("relation", "eq") == "eq" else f"pelo menos {total}"
    return f"{recebidos_txt} de {total_txt} encontrado(s) pela consulta."


def _falha_pagina(mensagem: str, causa: Exception) -> NoReturn:
    """Propaga falha de página com a causa original preservada."""
    raise ColetaParcialError(
        mensagem,
        resultado=pd.DataFrame(),
        falhas=[(None, None, causa)],
    ) from causa


def _total_primeira_pagina(api_response: dict[str, Any], alias: str, pagina: int) -> dict[str, Any]:
    """Valida o total informado pela primeira página."""
    total_info = api_response.get("hits", {}).get("total")
    if total_info is not None and not isinstance(total_info, dict):
        causa = ValueError("Campo 'hits.total' da resposta DataJud deve ser um objeto.")
        mensagem = (
            f"{_mensagem_falha_parcial(alias, pagina, 0, None)} "
            "Resposta inválida: campo 'hits.total' deve ser um objeto."
        )
        _falha_pagina(mensagem, causa)
    total_info = total_info or {}
    logger.info(
        "Total de processos encontrados para %s: %s (%s)",
        alias,
        total_info.get("value", "?"),
        total_info.get("relation", "eq"),
    )
    return total_info


def _hits_da_pagina(
    api_response: dict[str, Any],
    alias: str,
    pagina: int,
    recebidos: int,
    total_info: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Valida a estrutura dos resultados antes do uso do cursor."""
    diagnostico = _mensagem_falha_parcial(alias, pagina, recebidos, total_info)
    hits_obj = api_response.get("hits")
    if not isinstance(hits_obj, dict):
        causa: Exception = TypeError("Campo 'hits' da resposta DataJud deve ser um objeto.")
        _falha_pagina(f"{diagnostico} Resposta inválida: campo 'hits' deve ser um objeto.", causa)
    if "hits" not in hits_obj:
        causa = ValueError("Campo obrigatório 'hits.hits' ausente na resposta DataJud.")
        _falha_pagina(f"{diagnostico} Resposta inválida: campo 'hits.hits' ausente.", causa)
    hits = hits_obj["hits"]
    if not isinstance(hits, list):
        causa = ValueError("Campo 'hits.hits' da resposta DataJud deve ser uma lista.")
        _falha_pagina(f"{diagnostico} Resposta inválida: campo 'hits.hits' deve ser uma lista.", causa)
    if any(not isinstance(hit, dict) for hit in hits):
        causa = TypeError("Cada elemento de 'hits.hits' da resposta DataJud deve ser um objeto.")
        _falha_pagina(f"{diagnostico} Resposta inválida: cada hit deve ser um objeto.", causa)
    return hits


def _verificar_termino_prematuro(
    hits: list[dict[str, Any]],
    effective_size: int,
    total_info: dict[str, Any] | None,
    percorridos: int,
    contexto: _FimPagina,
) -> None:
    """Sinaliza página vazia ou curta antes do total exato.

    Vale com e sem ``paginas``: ``percorridos`` conta todas as páginas
    percorridas pelo cursor, inclusive as que ``paginas`` descarta, então
    uma página curta antes do total é falha mesmo quando a última página
    pedida ainda não chegou.
    """
    total_exato = _total_exato(total_info)
    if total_exato is None or percorridos >= total_exato:
        return
    if not hits:
        causa = RuntimeError("Página vazia antes de alcançar o total exato da consulta.")
    elif len(hits) < effective_size:
        causa = RuntimeError("Página curta antes de alcançar o total exato da consulta.")
    else:
        return
    diagnostico = _mensagem_falha_parcial(contexto.alias, contexto.pagina, contexto.recebidos, total_info)
    _falha_pagina(f"{diagnostico} Paginação encerrada prematuramente: {causa}", causa)


def _total_exato(total_info: dict[str, Any] | None) -> int | None:
    """Total informado pela consulta quando exato (``relation == "eq"``); ``None`` nos outros casos."""
    if not total_info or total_info.get("relation", "eq") != "eq":
        return None
    total = total_info.get("value")
    return total if isinstance(total, int) and not isinstance(total, bool) else None


def _verificar_fim_pagina(
    hits: list[dict[str, Any]],
    effective_size: int,
    total_info: dict[str, Any] | None,
    percorridos: int,
    contexto: _FimPagina,
) -> None:
    """Verifica cursor pendente e término prematuro após consumir a página."""
    total_exato = _total_exato(total_info)
    cursor_ausente = len(hits) >= effective_size and not isinstance(hits[-1].get("sort"), list)
    pagina_pendente = contexto.last_page is None or contexto.pagina < contexto.last_page
    total_esgotado = total_exato is not None and percorridos >= total_exato
    if cursor_ausente and pagina_pendente and not total_esgotado:
        mensagem = (
            f"DataJud: cursor search_after ausente no alias {contexto.alias!r} "
            f"após a página {contexto.pagina}; não foi possível consultar a próxima página."
        )
        _falha_pagina(mensagem, RuntimeError(mensagem))
    _verificar_termino_prematuro(hits, effective_size, total_info, percorridos, contexto)


def _verificar_shards(
    api_response: dict[str, Any],
    total_info: dict[str, Any] | None,
    contexto: _FimPagina,
) -> None:
    """Sinaliza resposta parcial do Elasticsearch (``_shards.failed > 0``), mesmo com HTTP 200.

    Com shards falhos, a página pode vir incompleta ou vazia, e o cursor dela
    pularia os registros perdidos; por isso a coleta do alias para aqui.
    ``_shards`` ausente conta como resposta completa.
    """
    shards = api_response.get("_shards")
    falhos = shards.get("failed") if isinstance(shards, dict) else None
    if not isinstance(falhos, int) or isinstance(falhos, bool) or falhos <= 0:
        return
    total = cast(dict[str, Any], shards).get("total")
    de_total = f" de {total}" if isinstance(total, int) and not isinstance(total, bool) else ""
    causa = RuntimeError(f"{falhos}{de_total} shard(s) falharam no Elasticsearch; a página pode estar incompleta.")
    diagnostico = _mensagem_falha_parcial(contexto.alias, contexto.pagina, contexto.recebidos, total_info)
    _falha_pagina(f"{diagnostico} Resposta parcial: {causa}", causa)


def _verificar_pagina_vazia(
    api_response: dict[str, Any],
    effective_size: int,
    total_info: dict[str, Any] | None,
    percorridos: int,
    contexto: _FimPagina,
) -> None:
    """Detecta página vazia inconsistente antes de entregá-la ao consumidor.

    A falha de shards vem primeiro: sem hits, não há o que preservar da
    página, e ela passaria por fim legítimo ou por término prematuro.
    ``hits.hits`` já passou por :func:`_hits_da_pagina`.
    """
    hits = api_response["hits"]["hits"]
    if not hits:
        _verificar_shards(api_response, total_info, contexto)
        _verificar_termino_prematuro(hits, effective_size, total_info, percorridos, contexto)


def _verificar_data_frame_vazio(
    api_response: dict[str, Any],
    alias: str,
    pagina: int,
    recebidos: int,
    total_info: dict[str, Any] | None,
) -> None:
    """Distingue fim vazio legítimo de hits que não geraram dados úteis."""
    if not api_response["hits"]["hits"]:
        return
    causa = ValueError("A página contém hits, mas não produziu dados utilizáveis no DataFrame.")
    mensagem = (
        f"{_mensagem_falha_parcial(alias, pagina, recebidos, total_info)} "
        "A resposta continha hits, mas o parsing não produziu dados utilizáveis."
    )
    _falha_pagina(mensagem, causa)


def _total_para_diagnostico(
    api_response: dict[str, Any],
    pagina: int,
    total_info: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Guarda o total da primeira página para diagnosticar falhas posteriores."""
    if pagina != 1:
        return total_info
    hits = api_response.get("hits")
    if isinstance(hits, dict) and isinstance(hits.get("total"), dict):
        return cast(dict[str, Any], hits["total"])
    return total_info
