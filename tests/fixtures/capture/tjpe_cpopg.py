"""Captura os samples do ``cpopg`` do TJPE (PJe de 1º grau, atrás do AWS WAF).

Rodar da raiz do repositório, com o extra ``waf`` (o Playwright resolve o
desafio quando ele aparece)::

    uv sync --extra dev --extra waf
    uv run playwright install chromium
    uv run python -m tests.fixtures.capture.tjpe_cpopg

Os arquivos gravados em ``tests/tjpe/samples/cpopg/`` e o que muda entre
capturas estão no README desta pasta (seção "TJPE cpopg").

Formulário, buscas e detalhe saem do ``cpopg_download`` de
:class:`TJPEConsultaPublicaScraper`, o fluxo de produção, por um hook de
resposta na sessão: se o TJPE deixar de aceitar o que o raspador manda, este
script quebra antes. Quando o WAF desafia, o raspador obtém o cookie pelo
Playwright e repete a requisição, e o arquivo guarda só a resposta repetida,
com os bytes como vieram. O desafio em si (``waf_challenge.html``) vem de um
cliente de linha de comando, que o WAF desafia sempre (conferido em
26/11/2026); as chaves ``key``, ``iv`` e ``context`` mudam a cada resposta e
não identificam ninguém. Nada é gravado antes de todas as respostas serem
conferidas.
"""
from __future__ import annotations

import logging

import requests

from juscraper.core.waf import eh_desafio_waf
from juscraper.courts._trf.download import DETAIL_PATH, LISTVIEW_PATH, extract_documento_urls
from juscraper.courts.tjpe.consulta_publica import TJPEConsultaPublicaScraper

from ._util import dump, respostas_do_cpopg, rotas, samples_dir_for

logger = logging.getLogger(__name__)

# Execução fiscal do Município do Cabo de Santo Agostinho contra uma pessoa
# jurídica (sociedade limitada): processo público, sem pessoa física nas
# partes, arquivado definitivamente, com até 15 movimentações e dois
# documentos visíveis sem login (as execuções com mais documentos tinham CPF
# nas partes).
FOUND_CNJ = "00147006920218172370"

# CNJ com a forma de um processo do TJPE (segmento 8, tribunal 17) e ano 2099,
# para passar pela máscara do formulário; a busca volta sem token ``ca``.
MISSING_CNJ = "00000000020998170001"

# Cliente sem cara de navegador que pede HTML: o WAF desafia toda vez. Só estes
# dois cabeçalhos; com os padrões do ``requests`` (``Accept-Encoding``,
# ``Connection``) o WAF deixa passar.
HEADERS_DESAFIO = {"User-Agent": "curl/8.7.1", "Accept": "text/html"}


def capturar_desafio() -> bytes:
    """A página de desafio do WAF do TJPE."""
    url = TJPEConsultaPublicaScraper.BASE_URL + LISTVIEW_PATH
    session = requests.Session()
    session.headers.clear()
    session.headers.update(HEADERS_DESAFIO)
    resp = session.get(url, timeout=30)
    if not eh_desafio_waf(resp) or resp.status_code != 202:
        raise RuntimeError(
            f"[tjpe] esperava o desafio do WAF (HTTP 202) em {url}, veio HTTP {resp.status_code}"
        )
    return resp.content


def capturar_consulta() -> dict[str, bytes]:
    """Formulário, buscas e detalhe, pelo ``cpopg_download`` do raspador."""
    scraper = TJPEConsultaPublicaScraper(sleep_time=0.5)
    listview = scraper.BASE_URL + LISTVIEW_PATH
    detalhe = scraper.BASE_URL + DETAIL_PATH

    html, respostas = respostas_do_cpopg(scraper, FOUND_CNJ, descartar=eh_desafio_waf)
    # Sem página extra de movimentações ou documentos: o contrato só registra estas três.
    esperado = [f"GET {listview}", f"POST {listview}", f"GET {detalhe}"]
    obtidas = rotas(respostas)
    if html is None or obtidas != esperado:
        raise RuntimeError(
            f"[tjpe] {FOUND_CNJ}: esperava formulário, busca e detalhe numa página só, "
            f"veio {obtidas} (processo arquivado, em segredo ou grande demais?)"
        )
    n_docs = len(extract_documento_urls(html))
    if n_docs < 2:
        raise RuntimeError(f"[tjpe] {FOUND_CNJ} tem {n_docs} documento(s); o contrato das peças precisa de 2 ou mais")
    nomes = ("form_initial.html", "search_one_result.html", "detail_normal.html")
    arquivos = {nome: resp.content for nome, resp in zip(nomes, respostas, strict=True)}

    # Sem token ``ca``, o download para na busca: só um POST.
    _, respostas = respostas_do_cpopg(scraper, MISSING_CNJ, descartar=eh_desafio_waf)
    obtidas = rotas(respostas)
    if obtidas != [f"POST {listview}"]:
        raise RuntimeError(f"[tjpe] {MISSING_CNJ}: esperava uma busca sem resultado, veio {obtidas}")
    arquivos["search_no_results.html"] = respostas[0].content
    return arquivos


def main() -> None:
    """Grava todos os samples do ``cpopg`` do TJPE, só depois de conferir todas as respostas."""
    # O desafio vem antes: logo depois da consulta do raspador, o WAF chegou a
    # deixar o cliente de linha de comando passar (HTTP 200, 26/11/2026).
    desafio = capturar_desafio()
    arquivos = {**capturar_consulta(), "waf_challenge.html": desafio}
    dest = samples_dir_for("tjpe", "cpopg")
    for nome, conteudo in arquivos.items():
        dump(dest / nome, conteudo)
        logger.info("[tjpe] cpopg/%s (%d bytes)", nome, len(conteudo))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
