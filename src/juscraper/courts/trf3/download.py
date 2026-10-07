"""Camada HTTP da consulta pública do PJe do TRF3 (API JSON).

O endereço antigo da consulta (``pje1g.trf3.jus.br/pje/ConsultaPublica/listView.seam``)
redireciona para uma aplicação Angular em ``pje1g-consultapublica.trf3.jus.br``,
que consome uma API JSON sob ``/v1``. O 2º grau mudou da mesma forma
(``pje2g-consultapublica.trf3.jus.br``), com a mesma API. Todas as rotas são
``GET`` e respondem no envelope
``{"status", "code", "messages", "result", "pageInfo"}``.

Uma consulta por CNJ faz estas requisições:

1. ``/v1/processos?page=0&numeroProcesso=<CNJ formatado>`` devolve a lista de
   processos com o ``idProcesso``, um token opaco que identifica o processo
   nas rotas seguintes.
2. ``/v1/processos/<id>/dados`` traz os metadados (classe, assunto, órgão).
3. ``poloAtivo``, ``poloPassivo``, ``outrosInteressados``, ``movimentacoes`` e
   ``documentos`` são paginados. O parâmetro ``page`` é 0-based, enquanto
   ``pageInfo.current`` e ``pageInfo.last`` são 1-based: ``page=0`` devolve
   ``current=1``, e a última página é ``page=last-1``.

O token muda a cada busca, mas continua válido em outra sessão, então o
download das peças não precisa repetir a busca.

A aplicação envia em toda chamada o cabeçalho ``x-pagina-origem`` com a URL da
tela que fez a chamada; :func:`build_pagina_origem_headers` o reproduz. O
Akamai na frente do portal segura sem resposta parte das requisições que não
parecem vir de navegador, por isso a sessão usa :data:`API_HEADERS`.
"""
# pylint: disable=protected-access
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

from ...core.exceptions import RetryExhaustedError
from ...core.http import RequestFn
from .._trf.download import BROWSER_HEADERS, _check_bot_challenge

logger = logging.getLogger("juscraper.trf3")

BASE_URL_1G = "https://pje1g-consultapublica.trf3.jus.br"
BASE_URL_2G = "https://pje2g-consultapublica.trf3.jus.br"
PROCESSOS_PATH = "/v1/processos"
DOCUMENTOS_PATH = "/v1/documentos"

#: Recursos paginados de um processo, na ordem em que são baixados. As chaves
#: são os nomes das rotas e também as chaves do dicionário bruto devolvido por
#: :func:`baixar_processo`.
RECURSOS_PAGINADOS: tuple[str, ...] = (
    "poloAtivo",
    "poloPassivo",
    "outrosInteressados",
    "movimentacoes",
    "documentos",
)

# Cabeçalhos de uma chamada XHR do navegador. Os de navegação de página
# (``Upgrade-Insecure-Requests``, ``Sec-Fetch-User``) saem, e os ``Sec-Fetch-*``
# passam a descrever uma chamada ``cors`` da própria origem, como faz o Chrome
# ao executar a aplicação Angular.
API_HEADERS: dict[str, str] = {
    **{
        chave: valor
        for chave, valor in BROWSER_HEADERS.items()
        if chave not in ("Upgrade-Insecure-Requests", "Sec-Fetch-User")
    },
    "Accept": "application/json, text/plain, */*",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def build_pagina_origem_headers(base_url: str, rota: str) -> dict[str, str]:
    """Monta o cabeçalho ``x-pagina-origem`` que a aplicação envia em toda chamada.

    ``rota`` é a rota da tela que dispara a chamada: ``"/"`` para a busca,
    ``"/processo/<id>"`` para o detalhe.
    """
    return {"x-pagina-origem": f"{base_url}{rota}", "Referer": f"{base_url}{rota}"}


def build_busca_params(numero_processo: str, page: int = 0) -> dict[str, Any]:
    """Monta a query string da busca por número de processo.

    ``numero_processo`` vai com máscara (``NNNNNNN-DD.AAAA.J.TR.OOOO``), como a
    aplicação envia.
    """
    return {"page": page, "numeroProcesso": numero_processo}


def busca_url(base_url: str) -> str:
    """URL da busca de processos."""
    return f"{base_url}{PROCESSOS_PATH}"


def recurso_url(base_url: str, id_processo: str, recurso: str) -> str:
    """URL de um recurso do processo (``dados`` ou um de :data:`RECURSOS_PAGINADOS`)."""
    return f"{base_url}{PROCESSOS_PATH}/{id_processo}/{recurso}"


def documento_download_url(base_url: str, id_documento: str) -> str:
    """URL que devolve o PDF de um documento do processo."""
    return f"{base_url}{DOCUMENTOS_PATH}/{id_documento}/download"


def _guarda_bot(tribunal: str) -> Callable[[requests.Response], None]:
    return lambda resp: _check_bot_challenge(resp, tribunal)


def _get_json(
    request_fn: RequestFn,
    url: str,
    *,
    base_url: str,
    rota: str,
    tribunal: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Faz um ``GET`` na API e devolve o envelope JSON.

    Raises:
        BotChallengeBlockedError: 403 ``Access Denied`` do Akamai.
        ValueError: Envelope com ``status`` diferente de ``"ok"``.
    """
    resp = request_fn(
        "GET",
        url,
        params=params,
        headers=build_pagina_origem_headers(base_url, rota),
        perfil="api",
        expect_json=True,
        on_response=_guarda_bot(tribunal),
    )
    data: dict[str, Any] = resp.json()
    if data.get("status") != "ok":
        raise ValueError(f"{tribunal}: resposta da API com status {data.get('status')!r} em {url}: {data}")
    return data


def buscar_processo(
    request_fn: RequestFn,
    base_url: str,
    numero_processo: str,
    tribunal: str = "TRF3",
) -> dict[str, Any]:
    """Busca o processo pelo número e devolve o envelope da busca."""
    return _get_json(
        request_fn,
        busca_url(base_url),
        base_url=base_url,
        rota="/",
        tribunal=tribunal,
        params=build_busca_params(numero_processo),
    )


def baixar_recurso_paginado(
    request_fn: RequestFn,
    base_url: str,
    id_processo: str,
    recurso: str,
    *,
    tribunal: str = "TRF3",
    sleep_time: float = 0.0,
) -> list[dict[str, Any]]:
    """Baixa todas as páginas de um recurso paginado do processo.

    Devolve a lista dos envelopes, uma entrada por página. A primeira página
    informa em ``pageInfo.last`` quantas páginas existem (1-based); as demais
    são pedidas com ``page`` 0-based, de ``1`` a ``last - 1``.
    """
    url = recurso_url(base_url, id_processo, recurso)
    rota = f"/processo/{id_processo}"
    primeira = _get_json(request_fn, url, base_url=base_url, rota=rota, tribunal=tribunal, params={"page": 0})
    paginas = [primeira]
    ultima = int((primeira.get("pageInfo") or {}).get("last") or 1)
    for page in range(1, ultima):
        if sleep_time:
            time.sleep(sleep_time)
        paginas.append(
            _get_json(request_fn, url, base_url=base_url, rota=rota, tribunal=tribunal, params={"page": page})
        )
    return paginas


def _escolher_processo(busca: dict[str, Any], numero_processo: str) -> dict[str, Any] | None:
    """Escolhe, entre os resultados da busca, o processo com o número pedido.

    A busca por número devolve no máximo um processo nos casos observados; a
    conferência pelo número evita aceitar um resultado de outro processo se a
    API passar a fazer busca aproximada.
    """
    resultados: list[dict[str, Any]] = busca.get("result") or []
    for item in resultados:
        if item.get("numeroProcesso") == numero_processo:
            return item
    return None


def baixar_processo(
    request_fn: RequestFn,
    base_url: str,
    numero_processo: str,
    *,
    tribunal: str = "TRF3",
    sleep_time: float = 0.0,
) -> dict[str, Any] | None:
    """Baixa os envelopes brutos de um processo, ou ``None`` se a busca não o achar.

    O dicionário devolvido tem as chaves ``"busca"`` (item da busca),
    ``"dados"`` (envelope de ``/dados``) e uma chave por recurso de
    :data:`RECURSOS_PAGINADOS`, com a lista de envelopes de cada página.

    Um recurso paginado que a API responde com erro HTTP depois das
    tentativas fica ``None`` e o resto do processo segue. A API responde 500
    de forma reproduzível ao ``poloPassivo`` de alguns mandados de segurança,
    e perder o processo inteiro por isso descartaria dados que vieram certos.
    Erro de rede e erro em ``/dados`` continuam derrubando o processo.
    """
    busca = buscar_processo(request_fn, base_url, numero_processo, tribunal)
    item = _escolher_processo(busca, numero_processo)
    if item is None:
        return None
    id_processo = item["idProcesso"]
    bruto: dict[str, Any] = {"busca": item}
    bruto["dados"] = _get_json(
        request_fn,
        recurso_url(base_url, id_processo, "dados"),
        base_url=base_url,
        rota=f"/processo/{id_processo}",
        tribunal=tribunal,
    )
    for recurso in RECURSOS_PAGINADOS:
        try:
            bruto[recurso] = baixar_recurso_paginado(
                request_fn, base_url, id_processo, recurso, tribunal=tribunal, sleep_time=sleep_time
            )
        except (RetryExhaustedError, requests.HTTPError) as exc:
            logger.warning("%s: %s de %s falhou: %s", tribunal, recurso, numero_processo, exc)
            bruto[recurso] = None
    return bruto


def baixar_documento(
    request_fn: RequestFn,
    base_url: str,
    id_documento: str,
    id_processo: str,
    *,
    tribunal: str = "TRF3",
) -> bytes:
    """Baixa o PDF de um documento do processo.

    A rota responde 415 sem ``Content-Type: application/json``, mesmo sendo
    ``GET``; a aplicação manda esse cabeçalho junto com ``Accept:
    application/pdf``. Documentos de texto (``binario=False``) e arquivos
    anexados (``binario=True``) saem em PDF pela mesma rota.

    Raises:
        BotChallengeBlockedError: 403 ``Access Denied`` do Akamai.
        ValueError: Resposta sem ``Content-Type`` de PDF.
    """
    url = documento_download_url(base_url, id_documento)
    headers = {
        **build_pagina_origem_headers(base_url, f"/processo/{id_processo}"),
        "Content-Type": "application/json",
        "Accept": "application/pdf",
    }
    resp = request_fn("GET", url, headers=headers, perfil="documento", on_response=_guarda_bot(tribunal))
    content_type = resp.headers.get("Content-Type", "")
    if "application/pdf" not in content_type:
        raise ValueError(f"{tribunal}: documento {id_documento} veio como {content_type!r}, não PDF")
    return resp.content
