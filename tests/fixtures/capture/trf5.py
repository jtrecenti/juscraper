"""Captura os samples do ``cpopg`` do TRF5 (PJe de 1º grau) no ar.

Rodar da raiz do repositório::

    uv run python -m tests.fixtures.capture.trf5

Grava em ``tests/trf5/samples/cpopg/`` ``form_initial.html``,
``search_one_result.html``, ``detail_normal.html`` e
``search_no_results.html``. O ``movs_page_2.html`` não sai daqui.

Os arquivos saem do ``cpopg_download`` de :class:`TRF5Scraper`, o fluxo de
produção, por um hook de resposta na sessão: se o TRF5 deixar de aceitar o que
o raspador manda, este script quebra antes, em vez de gravar samples velhos.
Os bytes são gravados como vieram, sem decodificar.
"""
from __future__ import annotations

import logging
import warnings

import requests

from juscraper.courts._trf.download import DETAIL_PATH, LISTVIEW_PATH, extract_ca_token
from juscraper.courts.trf5.client import TRF5Scraper

from ._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

# CNJ com um único resultado, de data/amostra_jf_primeiro_grau.csv: CEJUSC
# Maceió (AL).
FOUND_CNJ = "00584573120254058000"

# CNJ com a forma de um processo do TRF5, para passar pela máscara do
# formulário; a busca volta sem token ``ca``.
MISSING_CNJ = "00000000020994050000"


def _respostas_de(scraper: TRF5Scraper, cnj: str) -> tuple[str | None, list[requests.Response]]:
    """Roda o ``cpopg_download`` do raspador e devolve o detalhe e as respostas que ele usou."""
    respostas: list[requests.Response] = []

    def guardar(resp: requests.Response, *_args: object, **_kwargs: object) -> None:
        respostas.append(resp)

    scraper.session.hooks["response"].append(guardar)
    try:
        with warnings.catch_warnings():
            # Falha da consulta vira ``UserWarning`` no raspador; aqui ela interrompe a captura.
            warnings.simplefilter("error", UserWarning)
            (html,) = scraper.cpopg_download(cnj)
    finally:
        scraper.session.hooks["response"].remove(guardar)
    return html, respostas


def _rotas(respostas: list[requests.Response]) -> list[str]:
    return [f"{r.request.method} {(r.request.url or '').split('?')[0]}" for r in respostas]


def _descrever(respostas: list[requests.Response]) -> list[str]:
    """As rotas com o status HTTP, para a mensagem de erro (uma nova tentativa aparece aqui)."""
    return [f"{rota} -> HTTP {r.status_code}" for rota, r in zip(_rotas(respostas), respostas, strict=True)]


def main() -> None:
    """Grava os samples do ``cpopg`` do TRF5."""
    dest = samples_dir_for("trf5", "cpopg")
    scraper = TRF5Scraper(sleep_time=0.5)
    listview = scraper.BASE_URL + LISTVIEW_PATH
    detalhe = scraper.BASE_URL + DETAIL_PATH

    html, respostas = _respostas_de(scraper, FOUND_CNJ)
    # Sem página extra de movimentações ou documentos: o contrato só registra estas três.
    esperado = [f"GET {listview}", f"POST {listview}", f"GET {detalhe}"]
    if html is None or _rotas(respostas) != esperado:
        raise RuntimeError(
            f"[trf5] {FOUND_CNJ}: esperava formulário, busca e detalhe numa página só, "
            f"veio {_descrever(respostas)} (processo arquivado, em segredo, grande demais ou erro passageiro?)"
        )
    nomes = ("form_initial.html", "search_one_result.html", "detail_normal.html")
    for nome, resp in zip(nomes, respostas, strict=True):
        dump(dest / nome, resp.content)
        logger.info("[trf5] cpopg/%s (HTTP %d, %d bytes)", nome, resp.status_code, len(resp.content))

    html, respostas = _respostas_de(scraper, MISSING_CNJ)
    if html is not None or _rotas(respostas) != [f"POST {listview}"] or extract_ca_token(respostas[0].text):
        raise RuntimeError(f"[trf5] {MISSING_CNJ}: esperava uma busca sem resultado, veio {_descrever(respostas)}")
    dump(dest / "search_no_results.html", respostas[0].content)
    logger.info("[trf5] cpopg/search_no_results.html (%d bytes)", len(respostas[0].content))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
