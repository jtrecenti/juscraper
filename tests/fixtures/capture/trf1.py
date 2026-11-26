"""Captura samples do ``cpopg`` do TRF1 contra a API real.

Rodar a partir da raiz do repositório::

    uv run python -m tests.fixtures.capture.trf1

Passa pelos helpers de produção em :mod:`juscraper.courts._pje_api.download`
(``baixar_processo``, ``baixar_documento``) com um ``request_fn`` que grava
cada resposta crua. Se a API mudar de forma, a captura quebra antes de os
samples ficarem velhos.

Arquivos gravados em ``tests/trf1/samples/cpopg/``, um por requisição, com os
mesmos nomes de ``tests/fixtures/capture/trf3.py``:

* ``<cenario>_busca.json``: envelope de ``/v1/processos?numeroProcesso=...``;
* ``<cenario>_dados.json``: envelope de ``/v1/processos/<id>/dados``;
* ``<cenario>_<recurso>_page_<n>.json``: página ``n`` (0-based, o valor do
  parâmetro ``page``) de cada recurso paginado.

O sample de peça (``cpopg_pecas/documento.pdf``) é o PDF do primeiro
documento do cenário ``paginado``.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

import juscraper as jus
from juscraper.courts._pje_api.download import PROCESSOS_PATH, baixar_documento, baixar_processo, buscar_processo
from juscraper.courts.trf1.client import APLICACAO_1G

logger = logging.getLogger("juscraper.capture.trf1")

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES = REPO_ROOT / "tests" / "trf1" / "samples"

# Cenários: (nome do cenário, CNJ formatado).
# - paginado: JEF de Feira de Santana com movimentações em várias páginas.
# - normal: procedimento comum de Goiás, arquivado.
# - sem_resultado: CNJ que a busca não acha.
CENARIOS: list[tuple[str, str]] = [
    ("paginado", "1003063-27.2023.4.01.3304"),
    ("normal", "1008828-35.2021.4.01.3502"),
    ("sem_resultado", "0000000-00.2099.4.01.0000"),
]


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
        # A captura passa pelo retry do próprio raspador, que não é público.
        resp: requests.Response = scraper._request_with_retry(method, url, **kwargs)  # noqa: SLF001
        nome = _nome_arquivo(cenario, url, kwargs.get("params"))
        corpo = json.dumps(resp.json(), ensure_ascii=False, indent=1) + "\n"
        (dest / nome).write_text(corpo, encoding="utf-8")
        logger.info("  %s", nome)
        time.sleep(0.5)
        return resp

    return request_fn


def main() -> None:
    """Captura os samples do TRF1."""
    logging.basicConfig(level=logging.INFO, format="[trf1] %(message)s")
    scraper = jus.scraper("trf1", sleep_time=0.5)
    dest = SAMPLES / "cpopg"
    dest.mkdir(parents=True, exist_ok=True)
    for antigo in dest.glob("*.json"):
        antigo.unlink()
    brutos: dict[str, Any] = {}
    for cenario, cnj in CENARIOS:
        logger.info("cpopg/%s: %s", cenario, cnj)
        request_fn = _gravador(scraper, cenario, dest)
        if cenario == "sem_resultado":
            if buscar_processo(request_fn, APLICACAO_1G, cnj)["result"]:
                raise RuntimeError(f"[trf1] {cnj} deveria não ter resultado")
            continue
        bruto = baixar_processo(request_fn, APLICACAO_1G, cnj)
        if bruto is None:
            raise RuntimeError(f"[trf1] {cnj} sem resultado; escolha outro CNJ")
        brutos[cenario] = bruto
        for recurso in ("movimentacoes", "documentos", "poloAtivo", "poloPassivo"):
            info = bruto[recurso][0]["pageInfo"] if bruto[recurso] else "falhou"
            logger.info("  %s: %s", recurso, info)

    paginado = brutos["paginado"]
    id_documento = paginado["documentos"][0]["result"][0]["id"]
    request_fn = scraper._request_with_retry  # noqa: SLF001 (retry do raspador, como em _gravador)
    pdf = baixar_documento(request_fn, APLICACAO_1G, id_documento, paginado["busca"]["idProcesso"])
    pecas = SAMPLES / "cpopg_pecas"
    pecas.mkdir(parents=True, exist_ok=True)
    (pecas / "documento.pdf").write_bytes(pdf)
    logger.info("cpopg_pecas/documento.pdf (%d bytes)", len(pdf))


if __name__ == "__main__":
    main()
