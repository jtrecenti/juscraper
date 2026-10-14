"""Captura samples do ``cpopg`` e do ``cposg`` do TRF3 contra a API real.

Rodar a partir da raiz do repositório::

    uv run python -m tests.fixtures.capture.trf3

Passa pelos helpers de produção em :mod:`juscraper.courts.trf3.download`
(``baixar_processo``, ``baixar_documento``) com um ``request_fn`` que grava
cada resposta crua. Se a API mudar de forma, a captura quebra antes de os
samples ficarem velhos.

Arquivos gravados em ``tests/trf3/samples/<endpoint>/``, um por requisição:

* ``<cenario>_busca.json``: envelope de ``/v1/processos?numeroProcesso=...``;
* ``<cenario>_dados.json``: envelope de ``/v1/processos/<id>/dados``;
* ``<cenario>_<recurso>_page_<n>.json``: página ``n`` (0-based, o valor do
  parâmetro ``page``) de cada recurso paginado.

O sample de peça (``cpopg_pecas/documento.pdf``) é o PDF do primeiro
documento do cenário ``paginado`` do ``cpopg``.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

import juscraper as jus
from juscraper.courts.trf3.download import (
    BASE_URL_1G,
    BASE_URL_2G,
    PROCESSOS_PATH,
    baixar_documento,
    baixar_processo,
    buscar_processo,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES = REPO_ROOT / "tests" / "trf3" / "samples"

# Cenários de cada endpoint: (nome do cenário, CNJ formatado).
# - paginado: JEF de Barueri com 70 movimentações (5 páginas).
# - normal: movimentações em várias páginas e polo ativo vazio no 1º grau (a
#   API devolve ``pageInfo.last = 0`` para recurso sem itens). O CNJ existe
#   nos dois graus: cumprimento de sentença no 1º, apelação cível no 2º.
# - erro_recurso: mandado de segurança cujo ``poloPassivo`` a API responde com
#   500 a toda tentativa. Não há sample desse recurso; o contrato simula o 500.
# - pagina_unica: agravo de instrumento com todos os recursos numa página só.
#   O ``poloPassivo`` dele também responde 500.
# - sem_resultado: CNJ que a busca não acha naquele grau.
CENARIOS: dict[str, list[tuple[str, str]]] = {
    "cpopg": [
        ("paginado", "5003536-21.2025.4.03.6342"),
        ("normal", "5021122-65.2018.4.03.6100"),
        ("erro_recurso", "5025507-75.2026.4.03.6100"),
        ("sem_resultado", "0000000-00.2099.4.03.0000"),
    ],
    "cposg": [
        ("normal", "5021122-65.2018.4.03.6100"),
        ("pagina_unica", "5026242-75.2026.4.03.0000"),
        ("sem_resultado", "5003536-21.2025.4.03.6342"),
    ],
}
BASE_URLS = {"cpopg": BASE_URL_1G, "cposg": BASE_URL_2G}


def _nome_arquivo(cenario: str, url: str, params: dict[str, Any] | None) -> str:
    """Deriva o nome do sample a partir da rota pedida."""
    caminho = url.split(PROCESSOS_PATH, 1)[1].strip("/")
    if not caminho:
        return f"{cenario}_busca.json"
    recurso = caminho.split("/")[-1]
    if params and "page" in params:
        return f"{cenario}_{recurso}_page_{params['page']}.json"
    return f"{cenario}_{recurso}.json"


def _gravador(scraper, cenario: str, dest: Path):
    """``request_fn`` que delega ao retry do scraper e grava a resposta JSON."""

    def request_fn(method: str, url: str, **kwargs: Any) -> requests.Response:
        resp: requests.Response = scraper._request_with_retry(method, url, **kwargs)  # pylint: disable=protected-access
        nome = _nome_arquivo(cenario, url, kwargs.get("params"))
        corpo = json.dumps(resp.json(), ensure_ascii=False, indent=1) + "\n"
        (dest / nome).write_text(corpo, encoding="utf-8")
        print(f"[trf3]   {nome}")
        time.sleep(0.5)
        return resp

    return request_fn


def capturar_endpoint(scraper, endpoint: str) -> dict[str, Any]:
    """Captura os cenários de um endpoint e devolve os brutos de cada um."""
    dest = SAMPLES / endpoint
    dest.mkdir(parents=True, exist_ok=True)
    for antigo in dest.glob("*.json"):
        antigo.unlink()
    brutos: dict[str, Any] = {}
    for cenario, cnj in CENARIOS[endpoint]:
        print(f"[trf3] {endpoint}/{cenario}: {cnj}")
        request_fn = _gravador(scraper, cenario, dest)
        if cenario == "sem_resultado":
            busca = buscar_processo(request_fn, BASE_URLS[endpoint], cnj)
            if busca["result"]:
                raise RuntimeError(f"[trf3] {cnj} deveria não ter resultado em {endpoint}")
            continue
        bruto = baixar_processo(request_fn, BASE_URLS[endpoint], cnj)
        if bruto is None:
            raise RuntimeError(f"[trf3] {cnj} sem resultado em {endpoint}; escolha outro CNJ")
        brutos[cenario] = bruto
        for recurso in ("movimentacoes", "documentos", "poloAtivo", "poloPassivo"):
            info = bruto[recurso][0]["pageInfo"] if bruto[recurso] else "falhou"
            print(f"[trf3]   {recurso}: {info}")
    return brutos


def main() -> None:
    """Captura os samples do TRF3."""
    scraper = jus.scraper("trf3", sleep_time=0.5)
    brutos_1g = capturar_endpoint(scraper, "cpopg")
    capturar_endpoint(scraper, "cposg")

    bruto = brutos_1g["paginado"]
    id_documento = bruto["documentos"][0]["result"][0]["id"]
    request_fn = scraper._request_with_retry  # pylint: disable=protected-access
    pdf = baixar_documento(request_fn, BASE_URL_1G, id_documento, bruto["busca"]["idProcesso"])
    pecas = SAMPLES / "cpopg_pecas"
    pecas.mkdir(parents=True, exist_ok=True)
    (pecas / "documento.pdf").write_bytes(pdf)
    print(f"[trf3] cpopg_pecas/documento.pdf ({len(pdf)} bytes)")


if __name__ == "__main__":
    main()
