"""Capture cposg samples for TJMG (consulta processual de 2a instancia).

Run from repo root::

    python -m tests.fixtures.capture.tjmg_cposg
    python -m tests.fixtures.capture.tjmg_cposg --dest /tmp/tjmg_cposg  # para comparar

Roda o ``cposg_download`` real do ``TJMGScraper`` (mesmo ``request_fn``,
User-Agent e parametros) e grava, por um hook de resposta da sessao, os
bytes crus de cada pagina em ``tests/tjmg/samples/cposg/``:

- ``resultado_<cenario>.html`` — GET ``proc_resultado2.jsp?listaProcessos=<CNJ>``.
- ``partes_<...>.html`` — GET ``proc_partes_advogados2.jsp?listaProcessos=<numero TJMG>``
  para os recursos listados em ``CASOS``; os demais recursos sao baixados
  pelo raspador, mas nao gravados.

A consulta de 2a instancia nao tem captcha. O backend responde com quebras
de linha CRLF, gravadas como LF (como nos samples versionados), e as paginas
trazem a versao do sistema ("Versao de ...") e a data/hora da consulta ("Consulta
realizada em ..."): ao comparar uma recaptura com os samples, desconsiderar
essas diferencas. O ``partes_baixado`` e o recurso ``/002``; o ``/001`` do
mesmo CNJ e um agravo com outras partes (``partes_baixado_1``).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

import juscraper as jus

from ._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

# (cenario, numero consultado, {numero TJMG do recurso: nome do sample de partes})
CASOS: list[tuple[str, str, dict[str, str]]] = [
    ("single", "0000359-79.2020.8.13.0205", {"10000264083767001": "partes_single"}),
    (
        "multi",
        "5000344-57.2025.8.13.0461",
        {"10000261492847001": "partes_multi_1", "10000261492847002": "partes_multi_2"},
    ),
    ("segredo", "5005546-42.2023.8.13.0701", {}),
    (
        "baixado",
        "0037050-21.2010.8.13.0439",
        {"10439100037050001": "partes_baixado_1", "10439100037050002": "partes_baixado"},
    ),
    ("not_found", "1234567-89.2020.8.13.0024", {}),
]


def capturar(dest: Path) -> None:
    """Baixa cada caso de ``CASOS`` pelo ``cposg_download`` real e grava em ``dest``.

    As respostas ficam em memoria e so sao gravadas se todos os samples
    vierem: uma rodada com falha nao mistura samples novos e antigos. Resposta
    que nao seja HTTP 200 (o raspador repete e segue com aviso) nao conta;
    recurso fora de ``CASOS`` gera aviso. As quebras de linha sao normalizadas
    para LF, como nos samples versionados.
    """
    scraper = jus.scraper("tjmg")
    estado: dict = {"cenario": "", "partes": {}}
    capturados: dict[str, bytes] = {}

    def _guardar(resposta: requests.Response, *_args: object, **_kwargs: object) -> None:
        url = urlparse(resposta.request.url or "")
        numero = parse_qs(url.query).get("listaProcessos", [""])[0]
        rota = url.path.rsplit("/", 1)[-1]
        nome = None
        if rota == "proc_resultado2.jsp":
            nome = f"resultado_{estado['cenario']}"
        elif rota == "proc_partes_advogados2.jsp":
            nome = estado["partes"].get(numero)
            if nome is None:
                logger.warning("[tjmg/cposg/%s] recurso %s fora de CASOS; nao gravado", estado["cenario"], numero)
        if nome and resposta.status_code == 200:
            capturados[nome] = resposta.content.replace(b"\r\n", b"\n")
            logger.info("[tjmg/cposg/%s] %s?listaProcessos=%s -> %s.html", estado["cenario"], rota, numero, nome)

    scraper.session.hooks["response"].append(_guardar)
    for cenario, numero, partes in CASOS:
        estado.update(cenario=cenario, partes=partes)
        scraper.cposg_download(numero)

    esperados = {f"resultado_{cenario}" for cenario, _, _ in CASOS}
    esperados |= {nome for _, _, partes in CASOS for nome in partes.values()}
    faltantes = sorted(esperados - capturados.keys())
    if faltantes:
        raise SystemExit(f"TJMG cposg: samples nao gravados (falha na consulta?): {faltantes}")
    for nome, conteudo in capturados.items():
        dump(dest / f"{nome}.html", conteudo)


def main() -> None:
    """Captura os samples de cposg do TJMG."""
    parser = argparse.ArgumentParser(description="Captura os samples de cposg do TJMG.")
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Diretorio de saida (padrao: tests/tjmg/samples/cposg/).",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    capturar(args.dest or samples_dir_for("tjmg", "cposg"))


if __name__ == "__main__":
    main()
