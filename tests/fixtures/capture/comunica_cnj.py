"""Capture listar_comunicacoes samples for ComunicaCNJ.

Run from repo root::

    python -m tests.fixtures.capture.comunica_cnj

This script exercises ``ComunicaCNJScraper.listar_comunicacoes`` against
the real CNJ public Comunicacoes Processuais API and dumps the raw JSON
responses into ``tests/comunica_cnj/samples/listar_comunicacoes/`` for
use by the offline contract tests.

Cenarios capturados:

    results_normal_page_01.json   — multi-pagina, pagina 1: ``itens_por_pagina``
                                    items.
    results_normal_page_02.json   — multi-pagina, pagina 2: items residuais
                                    (forca break em ``client.py``).
    single_page.json              — busca cujos hits cabem em uma unica pagina
                                    (count <= itens_por_pagina).
    no_results.json               — ``items == []`` e ``count == 0``.

A querystring e construida por
``juscraper.aggregators.comunica_cnj.download.build_listar_comunicacoes_params`` —
a mesma funcao que ``client.py:listar_comunicacoes`` chama em producao.
Reexportada como ``build_params`` aqui apenas pelo nome curto e local;
capture e contrato compartilham a mesma fonte de verdade (regra 12 do
CLAUDE.md).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

from juscraper.aggregators.comunica_cnj.download import BASE_URL, DEFAULT_HEADERS
from juscraper.aggregators.comunica_cnj.download import build_listar_comunicacoes_params as build_params
from tests.fixtures.capture._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

TEXTO_TRUNC = 400  # Trunca o ``texto`` cru pos-captura — a API retorna
# strings de milhares de chars (HTML inline). O contrato so precisa do
# shape (presenca da chave + tipo); o conteudo integral nao e relevante.


def _sanitize(body: dict[str, Any]) -> dict[str, Any]:
    """Reduz o tamanho dos itens para manter os samples enxutos.

    A API publica do CNJ devolve, para cada comunicacao, um campo ``texto``
    com o HTML completo da publicacao do diario — varios kilobytes por
    item. O contrato precisa apenas validar shape (chaves presentes, tipos);
    truncar mantem ``tests/comunica_cnj/samples/`` longe do limite indicativo
    de ~20 MB do repo.
    """
    items = body.get("items") or body.get("itens") or []
    for item in items:
        if isinstance(item.get("texto"), str) and len(item["texto"]) > TEXTO_TRUNC:
            item["texto"] = item["texto"][:TEXTO_TRUNC] + "...[truncado]"
    return body


def _capture(
    session: requests.Session,
    params: dict[str, Any],
    dest: Path,
    filename: str,
) -> dict[str, Any]:
    response = session.get(BASE_URL, params=params, timeout=60)
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    body = _sanitize(body)
    dump(
        dest / filename,
        json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    n_items = len(body.get("items") or body.get("itens") or [])
    print(f"[comunica_cnj] wrote {filename} ({n_items} items, count={body.get('count')})")
    return body


def main() -> None:
    """Capture the four samples from the live ComunicaCNJ API.

    Sequencia intencional: a busca multi-pagina usa um termo bem comum
    (``"resolucao"``) com ``itens_por_pagina=10`` para garantir que a
    pagina 2 traga itens residuais < 10 (forca break do loop). O
    ``single_page`` filtra por intervalo de data estreito + termo raro.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dest = samples_dir_for("comunica_cnj", endpoint="listar_comunicacoes")

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    # 1) Multi-page (page 1): termo comum + itens_por_pagina=10.
    #    "resolucao" aparece em milhares de comunicacoes do CNJ; a primeira
    #    pagina volta exatos 10 items.
    params_p1 = build_params(
        pesquisa="resolucao",
        pagina=1,
        itens_por_pagina=10,
    )
    body_p1 = _capture(session, params_p1, dest, "results_normal_page_01.json")
    items_p1 = body_p1.get("items") or body_p1.get("itens") or []
    if len(items_p1) < 10:
        raise SystemExit(
            f"[comunica_cnj] page 1 returned {len(items_p1)} items, expected 10. "
            "Cannot capture page 2 deterministically."
        )

    # 2) Multi-page (page 2): mesma query, paginacao deterministica.
    params_p2 = build_params(
        pesquisa="resolucao",
        pagina=2,
        itens_por_pagina=10,
    )
    _capture(session, params_p2, dest, "results_normal_page_02.json")

    # 3) Single-page: termo + intervalo de data estreito que cabe em
    #    uma unica pagina. "embargos infringentes" + 1 dia historico
    #    geralmente devolve poucos itens.
    params_sp = build_params(
        pesquisa="embargos infringentes",
        pagina=1,
        itens_por_pagina=100,
        data_disponibilizacao_inicio="2024-06-03",
        data_disponibilizacao_fim="2024-06-03",
    )
    _capture(session, params_sp, dest, "single_page.json")

    # 4) No-results: termo que nao deve aparecer (slug improvavel).
    params_nr = build_params(
        pesquisa="juscraper_probe_zero_hits_xyzqwe",
        pagina=1,
        itens_por_pagina=100,
    )
    _capture(session, params_nr, dest, "no_results.json")

    print(f"[comunica_cnj] all samples written to {dest}")


if __name__ == "__main__":
    main()
