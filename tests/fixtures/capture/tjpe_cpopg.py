"""Captura os samples do ``cpopg`` do TJPE (PJe de 1º grau, atrás do AWS WAF).

Rodar da raiz do repositório, com o extra ``waf`` (o Playwright resolve o
desafio quando ele aparece)::

    uv sync --extra dev --extra waf
    uv run playwright install chromium
    uv run python -m tests.fixtures.capture.tjpe_cpopg

Grava em ``tests/tjpe/samples/cpopg/``:

- ``form_initial.html``: o formulário da consulta, de onde saem os ``j_idNNN``;
- ``search_one_result.html``: o fragmento Ajax da busca por :data:`FOUND_CNJ`,
  com o token ``ca`` do detalhe;
- ``detail_normal.html``: o detalhe de :data:`FOUND_CNJ`, com movimentações e
  documentos numa página só e ao menos dois documentos;
- ``search_no_results.html``: o fragmento da busca por :data:`MISSING_CNJ`,
  sem token ``ca``;
- ``waf_challenge.html``: a página de JavaScript que o WAF serve, com HTTP 202,
  no lugar do formulário.

Os quatro primeiros saem do ``cpopg_download`` de
:class:`TJPEConsultaPublicaScraper`, o fluxo de produção (funções de
:mod:`juscraper.courts._trf.download`), por um hook de resposta na sessão: se o
TJPE deixar de aceitar o que o raspador manda, este script quebra antes. O
WAF desafia o User-Agent de navegador do raspador de forma intermitente; quando
desafia, o raspador obtém o cookie pelo Playwright e repete a requisição, e o
arquivo guarda só a resposta repetida. Os bytes são gravados como vieram, sem
decodificar.

Para o desafio, um cliente de linha de comando que pede HTML (``curl`` +
``Accept: text/html``) é desafiado sempre (conferido em 26/11/2026). As chaves
``key``, ``iv`` e ``context`` mudam a cada resposta e não identificam ninguém.

Entre duas capturas seguidas (26/11/2026) mudaram o ``jsessionid``, o nó do
servidor (``[1g-031]``), o token dos links das peças e as chaves do desafio; as
buscas vieram idênticas. Os contratos leem esses valores do próprio sample. Se
o processo ganhar movimentações ou documentos além de uma página, o script para
e pede outro CNJ.
"""
from __future__ import annotations

import logging
import warnings

import requests

from juscraper.core.waf import eh_desafio_waf
from juscraper.courts._trf.download import DETAIL_PATH, LISTVIEW_PATH, extract_ca_token, extract_documento_urls
from juscraper.courts.tjpe.consulta_publica import TJPEConsultaPublicaScraper

from ._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

# Execução fiscal do Município do Cabo de Santo Agostinho contra uma pessoa
# jurídica (sociedade limitada): processo público, sem pessoa física nas
# partes, arquivado definitivamente, com até 15 movimentações e dois
# documentos visíveis sem login.
# Execuções com três ou mais documentos e até 15 movimentações que
# encontramos (nov/2026) tinham pessoa física ou MEI, com o CPF no nome, no
# polo passivo.
FOUND_CNJ = "00147006920218172370"

# CNJ com a forma de um processo do TJPE (segmento 8, tribunal 17) e ano 2099,
# para passar pela máscara do formulário; a busca volta sem token ``ca``.
MISSING_CNJ = "00000000020998170001"

# Cliente sem cara de navegador que pede HTML: o WAF desafia toda vez. Só estes
# dois cabeçalhos; com os padrões do ``requests`` (``Accept-Encoding``,
# ``Connection``) o WAF deixa passar.
HEADERS_DESAFIO = {"User-Agent": "curl/8.7.1", "Accept": "text/html"}


def capturar_desafio() -> None:
    """Grava a página de desafio do WAF do TJPE."""
    url = TJPEConsultaPublicaScraper.BASE_URL + LISTVIEW_PATH
    session = requests.Session()
    session.headers.clear()
    session.headers.update(HEADERS_DESAFIO)
    resp = session.get(url, timeout=30)
    if not eh_desafio_waf(resp) or resp.status_code != 202:
        raise RuntimeError(
            f"[tjpe] esperava o desafio do WAF (HTTP 202) em {url}, veio HTTP {resp.status_code}"
        )
    dump(samples_dir_for("tjpe", "cpopg") / "waf_challenge.html", resp.content)
    logger.info("[tjpe] cpopg/waf_challenge.html (%d bytes)", len(resp.content))


def _respostas_de(scraper: TJPEConsultaPublicaScraper, cnj: str) -> tuple[str | None, list[requests.Response]]:
    """Roda o ``cpopg_download`` do raspador e devolve o detalhe e as respostas que ele usou.

    Os desafios do WAF ficam de fora: a resposta que segue cada um é a
    requisição repetida com o cookie novo.
    """
    respostas: list[requests.Response] = []

    def guardar(resp: requests.Response, *_args: object, **_kwargs: object) -> None:
        respostas.append(resp)

    scraper.session.hooks["response"].append(guardar)
    try:
        with warnings.catch_warnings():
            # Falha da consulta vira aviso no raspador; aqui ela interrompe a captura.
            warnings.simplefilter("error")
            (html,) = scraper.cpopg_download(cnj)
    finally:
        scraper.session.hooks["response"].remove(guardar)
    return html, [r for r in respostas if not eh_desafio_waf(r)]


def _rotas(respostas: list[requests.Response]) -> list[str]:
    return [f"{r.request.method} {(r.request.url or '').split('?')[0]}" for r in respostas]


def capturar_consulta() -> None:
    """Grava formulário, buscas e detalhe pelo ``cpopg_download`` do raspador."""
    dest = samples_dir_for("tjpe", "cpopg")
    scraper = TJPEConsultaPublicaScraper(sleep_time=0.5)
    listview = scraper.BASE_URL + LISTVIEW_PATH
    detalhe = scraper.BASE_URL + DETAIL_PATH

    html, respostas = _respostas_de(scraper, FOUND_CNJ)
    # Sem página extra de movimentações ou documentos: o contrato só registra estas três.
    esperado = [f"GET {listview}", f"POST {listview}", f"GET {detalhe}"]
    if html is None or _rotas(respostas) != esperado:
        raise RuntimeError(
            f"[tjpe] {FOUND_CNJ}: esperava formulário, busca e detalhe numa página só, "
            f"veio {_rotas(respostas)} (processo arquivado, em segredo ou grande demais?)"
        )
    n_docs = len(extract_documento_urls(html))
    if n_docs < 2:
        raise RuntimeError(f"[tjpe] {FOUND_CNJ} tem {n_docs} documento(s); o contrato das peças precisa de 2 ou mais")
    nomes = ("form_initial.html", "search_one_result.html", "detail_normal.html")
    for nome, resp in zip(nomes, respostas, strict=True):
        dump(dest / nome, resp.content)
        logger.info("[tjpe] cpopg/%s (HTTP %d, %d bytes)", nome, resp.status_code, len(resp.content))

    html, respostas = _respostas_de(scraper, MISSING_CNJ)
    if html is not None or _rotas(respostas) != [f"POST {listview}"] or extract_ca_token(respostas[0].text):
        raise RuntimeError(f"[tjpe] {MISSING_CNJ}: esperava uma busca sem resultado, veio {_rotas(respostas)}")
    dump(dest / "search_no_results.html", respostas[0].content)
    logger.info("[tjpe] cpopg/search_no_results.html (%d bytes)", len(respostas[0].content))


def main() -> None:
    """Grava todos os samples do ``cpopg`` do TJPE."""
    capturar_consulta()
    capturar_desafio()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
