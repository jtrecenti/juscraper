"""Captura os samples do ``cpopg`` do TRF6 (eproc de 1º grau) no ar.

Rodar da raiz do repositório::

    uv run python -m tests.fixtures.capture.trf6

Grava em ``tests/trf6/samples/cpopg/`` ``form_initial.html``,
``detail_normal.html``, ``search_no_results.html`` e
``search_bad_captcha.html``. O ``detail_cumprimento_sentenca.html`` e o
``form_desafio_f5.html`` não saem daqui.

Formulário, detalhe e busca sem resultado saem do ``cpopg_download`` de
:class:`TRF6Scraper`, o fluxo de produção, por um hook de resposta na sessão:
se o TRF6 deixar de aceitar o que o raspador manda, este script quebra antes,
em vez de gravar samples velhos. Das tentativas do raspador, fica só a última,
a do captcha aceito. O captcha errado de propósito não passa pelo
``cpopg_download``, que tenta de novo até acertar: sai de ``fetch_form`` e
``submit_search``, as funções que o raspador usa, com o mesmo hook. Os bytes
são gravados como vieram, sem decodificar, e só depois de conferidas todas as
respostas.

Precisa do extra ``txtcaptcha`` (``uv pip install txtcaptcha``); o resolvedor
baixa um modelo do HuggingFace na primeira chamada.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import parse_qs, urlparse

import requests

from juscraper.courts.trf6.client import TRF6Scraper
from juscraper.courts.trf6.download import build_search_payload, fetch_form, is_captcha_error, submit_search
from juscraper.utils.cnj import format_cnj

from ._util import dump, respostas_da_sessao, respostas_do_cpopg, samples_dir_for

logger = logging.getLogger(__name__)

# Processo do JEF da 3ª Vara Cível e JEF de Juiz de Fora (MG), de
# data/amostra_jf_primeiro_grau.csv.
FOUND_CNJ = "10052295520234063801"

# CNJ com a forma de um processo do TRF6, para passar pela máscara do
# formulário; o eproc devolve o formulário, sem erro, quando nada casa.
MISSING_CNJ = "00000000020994060000"

# Segundos entre as três consultas: cada ``cpopg_download`` leva um CNJ só, e
# a pausa do raspador vale apenas entre CNJs do mesmo lote.
PAUSA = 2

# Cada tentativa do raspador pede o formulário e manda a busca ao mesmo
# controlador; o que distingue as requisições é o parâmetro ``acao``. A busca
# que acha o processo redireciona (302) para o detalhe; as outras respondem ao
# próprio POST, com o formulário.
FORMULARIO = "GET processo_consulta_publica"
BUSCA = "POST processo_consulta_publica"
DETALHE = "GET processo_seleciona_publica"


def _acoes(respostas: list[requests.Response]) -> list[str]:
    """``MÉTODO acao`` de cada resposta."""
    return [f"{r.request.method} {parse_qs(urlparse(r.url).query).get('acao', [''])[0]}" for r in respostas]


def _tentativa_aceita(cnj: str, respostas: list[requests.Response], ultima: str) -> tuple[bytes, bytes]:
    """Formulário e resposta da busca na última tentativa, a do captcha aceito.

    As tentativas anteriores, de captcha recusado, são pares de formulário e
    busca; a última termina em ``ultima``.
    """
    obtidas = _acoes(respostas)
    recusadas = len(obtidas) // 2 - 1
    if obtidas != [FORMULARIO, BUSCA] * recusadas + [FORMULARIO, ultima]:
        raise RuntimeError(f"[trf6] {cnj}: esperava formulários e buscas terminando em {ultima!r}, veio {obtidas}")
    logger.info("[trf6] %s: captcha aceito na tentativa %d", cnj, recusadas + 1)
    formulario, busca = respostas[-2:]
    return formulario.content, busca.content


def capturar_consulta(scraper: TRF6Scraper) -> dict[str, bytes]:
    """Formulário, detalhe e busca sem resultado, pelo ``cpopg_download`` do raspador.

    O conteúdo da última resposta já passou pelo ``fetch_detail``: ele só
    devolve HTML quando é o detalhe e só devolve ``None`` quando é o
    formulário de novo; o resto vira falha da consulta, que interrompe a
    captura.
    """
    html, respostas = respostas_do_cpopg(scraper, FOUND_CNJ)
    if html is None:
        raise RuntimeError(f"[trf6] {FOUND_CNJ}: a busca não trouxe o detalhe (processo arquivado ou em sigilo?)")
    formulario, detalhe = _tentativa_aceita(FOUND_CNJ, respostas, DETALHE)
    time.sleep(PAUSA)

    html, respostas = respostas_do_cpopg(scraper, MISSING_CNJ)
    if html is not None:
        raise RuntimeError(f"[trf6] {MISSING_CNJ}: o CNJ sintético casou com um processo; escolha outro")
    _, sem_resultado = _tentativa_aceita(MISSING_CNJ, respostas, BUSCA)

    return {
        "form_initial.html": formulario,
        "detail_normal.html": detalhe,
        "search_no_results.html": sem_resultado,
    }


def capturar_captcha_errado(scraper: TRF6Scraper) -> bytes:
    """A busca com um captcha errado de propósito."""
    with respostas_da_sessao(scraper.session) as respostas:
        fetch_form(scraper.session, timeout=scraper.timeout)
        payload = build_search_payload(format_cnj(FOUND_CNJ), "WRONG")
        busca = submit_search(scraper.session, payload, timeout=scraper.timeout)
    obtidas = _acoes(respostas)
    if obtidas != [FORMULARIO, BUSCA] or not is_captcha_error(busca):
        raise RuntimeError(f"[trf6] esperava o formulário e a recusa do captcha, veio {obtidas}")
    return respostas[-1].content


def main() -> None:
    """Grava os samples do ``cpopg`` do TRF6, só depois de conferir todas as respostas."""
    try:
        import txtcaptcha
    except ImportError as exc:
        raise SystemExit("tests/fixtures/capture/trf6.py precisa do txtcaptcha (`uv pip install txtcaptcha`).") from exc

    scraper = TRF6Scraper(max_captcha_attempts=5)
    arquivos = capturar_consulta(scraper)
    time.sleep(PAUSA)
    arquivos["search_bad_captcha.html"] = capturar_captcha_errado(scraper)

    dest = samples_dir_for("trf6", "cpopg")
    for nome, conteudo in arquivos.items():
        dump(dest / nome, conteudo)
        logger.info("[trf6] cpopg/%s (%d bytes)", nome, len(conteudo))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
