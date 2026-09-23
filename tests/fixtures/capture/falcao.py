"""Capture cjsg samples for the Falcao aggregator (Jurisprudencia Nacional da JT).

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
import time
from pathlib import Path
from typing import Any

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


def _truncar(valor: Any) -> Any:
    if isinstance(valor, str) and len(valor) > TEXTO_TRUNC:
        return valor[:TEXTO_TRUNC] + MARCA_TRUNC
    if isinstance(valor, dict):
        return {k: _truncar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_truncar(v) for v in valor]
    return valor


def _capture(session: requests.Session, session_id: str, dest: Path, colecao: str,
             pesquisa: str, arquivo: str) -> None:
    params = build_pesquisa_params(
        pesquisa=pesquisa,
        colecao=colecao,
        session_id=session_id,
        pagina=1,
        tamanho_pagina=TAMANHO_PAGINA,
    )
    resp = session.get(SEARCH_URL, params=params, timeout=60)
    verificar_resposta(resp)
    resp.raise_for_status()
    body = _truncar(resp.json())
    dump(dest / arquivo, json.dumps(body, ensure_ascii=False, indent=1).encode("utf-8"))
    print(f"[falcao] wrote {arquivo} ({len(body['documentos'])} docs, quantidadeTotal={body['quantidadeTotal']})")


def main() -> None:
    """Capture one page per collection plus the empty scenario."""
    dest = samples_dir_for("falcao", endpoint="pesquisa")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session_id = gerar_session_id()

    cenarios = [(colecao, PESQUISA, f"{colecao}_normal.json") for colecao in COLECOES]
    cenarios.append(("acordaos", PESQUISA_VAZIA, "acordaos_vazio.json"))
    for i, (colecao, pesquisa, arquivo) in enumerate(cenarios):
        if i:
            time.sleep(PAUSA)
        _capture(session, session_id, dest, colecao, pesquisa, arquivo)

    print(f"[falcao] all samples written to {dest}")


if __name__ == "__main__":
    main()
