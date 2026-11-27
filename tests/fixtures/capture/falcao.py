"""Capture listar_decisoes samples for the Falcao aggregator (Jurisprudencia Nacional da JT).

Run from repo root::

    python -m tests.fixtures.capture.falcao

Dispara buscas reais no endpoint ``/no-auth/pesquisa`` e grava o JSON cru em
``tests/falcao/samples/pesquisa/`` para os testes de contrato offline.

Cenarios capturados (busca ``"dano moral"``, 5 documentos por pagina):

    {colecao}_normal.json   — uma pagina de cada colecao de
                              :data:`juscraper.aggregators.falcao.schemas.COLECOES`.
                              Em ``precedentes``, a busca traz sumulas do TST
                              e precedentes regionais sem ``numero``.
    acordaos_vazio.json     — termo sem resultados (``documentos == []``).
    acordaos_ementa_inteira.json — página 2 de ``"horas extras"`` em
                              ``acordaos``, com a ``ementa`` sem truncar: traz
                              ementa em vários ``<p>``, documento HTML com
                              ``<style>`` e quebra de linha no meio da frase,
                              para os testes de ``html_para_texto``.

A querystring vem de
``juscraper.aggregators.falcao.download.build_pesquisa_params``, a mesma
funcao que ``client.py`` chama em producao, e as respostas passam por
``verificar_resposta`` como no scraper. O backend bloqueia o IP por horas
quando a janela de rate limit estoura (429 com
``x-rate-limit-retry-after-seconds``); por isso ha ``PAUSA`` entre as
requisicoes e o script para na primeira resposta de bloqueio.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, NamedTuple

import requests

from juscraper.aggregators.falcao.download import (
    DEFAULT_HEADERS,
    SEARCH_URL,
    build_pesquisa_params,
    gerar_session_id,
    verificar_resposta,
)
from juscraper.aggregators.falcao.schemas import COLECOES
from tests.fixtures.capture._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

PESQUISA = "dano moral"
PESQUISA_VAZIA = "juscraper_probe_zero_hits_xyzqwe"
TAMANHO_PAGINA = 5
PAUSA = 3.0

# Os campos de inteiro teor (``textoAcordao``, ``textoSentenca``,
# ``conteudoDecisao``, ``highlight*``) tem dezenas de kB por documento, com
# imagens em base64. O contrato so precisa do shape, entao strings longas sao
# truncadas aqui, e nao a mao.
TEXTO_TRUNC = 600
MARCA_TRUNC = "…[truncado]"


class Cenario(NamedTuple):
    colecao: str
    pesquisa: str
    arquivo: str
    inteiros: frozenset[str] = frozenset()
    pagina: int = 1


def _truncar(valor: Any, inteiros: frozenset[str] = frozenset()) -> Any:
    """Trunca as strings longas, menos as das chaves em ``inteiros``."""
    if isinstance(valor, str) and len(valor) > TEXTO_TRUNC:
        return valor[:TEXTO_TRUNC] + MARCA_TRUNC
    if isinstance(valor, dict):
        return {k: v if k in inteiros else _truncar(v, inteiros) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_truncar(v, inteiros) for v in valor]
    return valor


def _capture(session: requests.Session, session_id: str, dest: Path, cenario: Cenario) -> None:
    params = build_pesquisa_params(
        pesquisa=cenario.pesquisa,
        colecao=cenario.colecao,
        session_id=session_id,
        pagina=cenario.pagina,
        tamanho_pagina=TAMANHO_PAGINA,
    )
    resp = session.get(SEARCH_URL, params=params, timeout=60)
    verificar_resposta(resp)
    resp.raise_for_status()
    body = _truncar(resp.json(), cenario.inteiros)
    dump(dest / cenario.arquivo, json.dumps(body, ensure_ascii=False, indent=1).encode("utf-8"))
    total = body["quantidadeTotal"]
    logger.info("[falcao] wrote %s (%s docs, quantidadeTotal=%s)", cenario.arquivo, len(body['documentos']), total)


def main() -> None:
    """Capture one page per collection plus the empty scenario."""
    dest = samples_dir_for("falcao", endpoint="pesquisa")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session_id = gerar_session_id()

    cenarios = [Cenario(colecao, PESQUISA, f"{colecao}_normal.json") for colecao in COLECOES]
    cenarios.append(Cenario("acordaos", PESQUISA_VAZIA, "acordaos_vazio.json"))
    cenarios.append(Cenario(
        "acordaos", "horas extras", "acordaos_ementa_inteira.json", frozenset({"ementa"}), pagina=2,
    ))
    for i, cenario in enumerate(cenarios):
        if i:
            time.sleep(PAUSA)
        _capture(session, session_id, dest, cenario)

    logger.info("[falcao] all samples written to %s", dest)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
