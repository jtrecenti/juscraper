"""Registra no ``responses`` as respostas capturadas da API do TRF3.

Os samples ficam em ``tests/trf3/samples/<endpoint>/`` com os nomes que
``tests/fixtures/capture/trf3.py`` grava (``<cenario>_busca.json``,
``<cenario>_dados.json``, ``<cenario>_<recurso>_page_<n>.json``). Cada
cenário é registrado com matchers de query string e do cabeçalho
``x-pagina-origem``, então uma requisição fora do roteiro esperado cai sem
mock e vira ``ConnectionError``.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import responses
from responses import matchers

from juscraper.courts.trf3.download import RECURSOS_PAGINADOS, busca_url, recurso_url

SAMPLES = Path(__file__).parent / "samples"


def carregar(endpoint: str, nome: str) -> dict[str, Any]:
    """Lê um sample JSON do endpoint."""
    resultado: dict[str, Any] = json.loads((SAMPLES / endpoint / nome).read_text(encoding="utf-8"))
    return resultado


def numero_do_cenario(endpoint: str, cenario: str) -> str:
    """Número de processo (com máscara) de um cenário com resultado."""
    numero: str = carregar(endpoint, f"{cenario}_busca.json")["result"][0]["numeroProcesso"]
    return numero


def id_processo_do_cenario(endpoint: str, cenario: str) -> str:
    """Token ``idProcesso`` do cenário, que compõe as URLs do detalhe."""
    id_processo: str = carregar(endpoint, f"{cenario}_busca.json")["result"][0]["idProcesso"]
    return id_processo


def registrar_busca(base_url: str, endpoint: str, cenario: str, numero_processo: str) -> None:
    """Registra a busca do cenário, conferindo ``page=0``, o número e a origem."""
    responses.add(
        responses.GET,
        busca_url(base_url),
        json=carregar(endpoint, f"{cenario}_busca.json"),
        match=[
            matchers.query_param_matcher({"page": "0", "numeroProcesso": numero_processo}),
            matchers.header_matcher({"x-pagina-origem": f"{base_url}/"}),
        ],
    )


def registrar_processo(
    base_url: str,
    endpoint: str,
    cenario: str,
    *,
    status_recursos_sem_sample: int = 500,
    substituir: Mapping[str, list[dict[str, Any]]] | None = None,
) -> int:
    """Registra busca, ``/dados`` e todas as páginas de cada recurso do cenário.

    Recurso sem sample (o ``poloPassivo`` que a API responde com 500) recebe
    ``status_recursos_sem_sample``. ``substituir`` troca as páginas de um
    recurso por envelopes montados no teste (``{recurso: [page_0, page_1]}``).
    Devolve o número de páginas registradas, para o teste conferir que
    nenhuma sobrou.
    """
    numero = numero_do_cenario(endpoint, cenario)
    id_processo = id_processo_do_cenario(endpoint, cenario)
    origem = matchers.header_matcher({"x-pagina-origem": f"{base_url}/processo/{id_processo}"})
    registrar_busca(base_url, endpoint, cenario, numero)
    responses.add(
        responses.GET,
        recurso_url(base_url, id_processo, "dados"),
        json=carregar(endpoint, f"{cenario}_dados.json"),
        match=[origem],
    )
    paginas = 0
    substituir = substituir or {}
    for recurso in RECURSOS_PAGINADOS:
        url = recurso_url(base_url, id_processo, recurso)
        if recurso in substituir:
            for indice, envelope in enumerate(substituir[recurso]):
                responses.add(
                    responses.GET,
                    url,
                    json=envelope,
                    match=[matchers.query_param_matcher({"page": str(indice)}), origem],
                )
                paginas += 1
            continue
        arquivos = sorted(
            (SAMPLES / endpoint).glob(f"{cenario}_{recurso}_page_*.json"),
            key=lambda p: int(p.stem.rsplit("_", 1)[1]),
        )
        if not arquivos:
            responses.add(
                responses.GET,
                url,
                json={"status": status_recursos_sem_sample, "error": "Internal Server Error"},
                status=status_recursos_sem_sample,
            )
            continue
        for arquivo in arquivos:
            page = arquivo.stem.rsplit("_", 1)[1]
            responses.add(
                responses.GET,
                url,
                json=json.loads(arquivo.read_text(encoding="utf-8")),
                match=[matchers.query_param_matcher({"page": page}), origem],
            )
            paginas += 1
    return paginas


def itens_do_cenario(endpoint: str, cenario: str, recurso: str) -> list[dict[str, Any]]:
    """Concatena o ``result`` de todas as páginas de um recurso do cenário."""
    itens: list[dict[str, Any]] = []
    for arquivo in sorted((SAMPLES / endpoint).glob(f"{cenario}_{recurso}_page_*.json")):
        itens.extend(json.loads(arquivo.read_text(encoding="utf-8"))["result"])
    return itens


def envelope_paginado(itens: list[dict[str, Any]], tamanho: int = 15) -> list[dict[str, Any]]:
    """Reparte ``itens`` em envelopes de página no formato da API.

    ``pageInfo.current`` e ``pageInfo.last`` são 1-based, como nas respostas
    reais; ``tamanho`` é o ``size`` que a API usa para documentos (15).
    """
    blocos = [itens[i : i + tamanho] for i in range(0, len(itens), tamanho)] or [[]]
    return [
        {
            "status": "ok",
            "code": "200",
            "messages": [],
            "result": bloco,
            "pageInfo": {"current": n + 1, "last": len(blocos), "size": tamanho, "count": len(itens)},
        }
        for n, bloco in enumerate(blocos)
    ]


def documentos_em_duas_paginas() -> list[dict[str, Any]]:
    """Documentos reais de dois processos (13 + 8) repartidos em 2 páginas de 15.

    Nenhum processo capturado tem mais de 15 documentos; a fixture junta os
    itens reais do ``normal`` do 1º e do 2º grau para exercitar a segunda
    página do recurso ``documentos``.
    """
    itens = itens_do_cenario("cpopg", "normal", "documentos") + itens_do_cenario("cposg", "normal", "documentos")
    return envelope_paginado(itens)
