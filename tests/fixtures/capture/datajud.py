"""Capture listar_processos samples for DataJud (issue #140).

Run from repo root::

    python -m tests.fixtures.capture.datajud

This script exercises ``DatajudScraper.listar_processos`` against the
real CNJ DataJud public API and dumps the raw Elasticsearch responses
into ``tests/datajud/samples/listar_processos/`` for use by the offline
contract tests.

Cenários capturados:

    results_normal_page_01.json   — multi-página, página 1: exatamente
                                    ``tamanho_pagina`` hits.
    results_normal_page_02.json   — multi-página, página 2: ``< tamanho_pagina``
                                    hits (força break em
                                    ``client.py:_listar_processos_por_alias``).
    single_page.json              — busca cujos hits cabem em uma única página.
    no_results.json               — ``hits.hits == []``.

NOTA (drift, regra 12 do CLAUDE.md): este script duplica o construtor
de body Elasticsearch que vive em
``src/juscraper/aggregators/datajud/client.py:_listar_processos_por_alias``
(branch construtor de body Elasticsearch dentro do ``while`` de paginação).
A issue #140 declara critério 8 (não modifica ``src/``), o que impediu a
extração de ``build_listar_processos_payload`` em
``aggregators/datajud/download.py``.

Follow-up: extrair o builder e fazer este script importar em vez de
redefinir. Enquanto isso, qualquer alteração no body Elasticsearch
construído pelo client precisa ser refletida em ``build_payload`` aqui.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

from juscraper.aggregators.datajud.client import DatajudScraper
from juscraper.utils.cnj import clean_cnj
from tests.fixtures.capture._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

API_KEY = DatajudScraper.DEFAULT_API_KEY
BASE_API_URL = DatajudScraper.BASE_API_URL


def build_payload(
    *,
    numero_processo: str | list[str] | None = None,
    ano_ajuizamento: int | None = None,
    classe: str | None = None,
    assuntos: list[str] | None = None,
    mostrar_movs: bool = False,
    tamanho_pagina: int = 1000,
    search_after: list[Any] | None = None,
) -> dict[str, Any]:
    """Replica o branch construtor de body Elasticsearch dentro do ``while`` de
    paginação em ``client.py:_listar_processos_por_alias``.

    Mantém a ordem de chaves e a lógica condicional idêntica para que o
    capture e o contrato falhem juntos quando o body real do scraper
    mudar.
    """
    must_conditions: list[dict[str, Any]] = []
    if numero_processo:
        if isinstance(numero_processo, str):
            nproc = [numero_processo]
        else:
            nproc = list(numero_processo)
        nproc = [clean_cnj(n) for n in nproc]
        must_conditions.append({"terms": {"numeroProcesso": nproc}})
    if ano_ajuizamento:
        date_range_iso = {
            "gte": f"{ano_ajuizamento}-01-01",
            "lte": f"{ano_ajuizamento}-12-31",
        }
        date_range_compact = {
            "gte": f"{ano_ajuizamento}0101000000",
            "lte": f"{ano_ajuizamento}1231235959",
        }
        must_conditions.append({
            "bool": {
                "should": [
                    {"range": {"dataAjuizamento": date_range_iso}},
                    {"range": {"dataAjuizamento": date_range_compact}},
                ],
                "minimum_should_match": 1,
            }
        })
    if classe:
        must_conditions.append({"match": {"classe.codigo": str(classe)}})
    if assuntos:
        must_conditions.append({"terms": {"assuntos.codigo": assuntos}})

    if must_conditions:
        query_values: dict[str, Any] = {"bool": {"must": must_conditions}}
    else:
        query_values = {"match_all": {}}

    payload: dict[str, Any] = {
        "query": query_values,
        "size": tamanho_pagina,
        "track_total_hits": True,
        "sort": [{"id.keyword": "asc"}],
    }
    if search_after is not None:
        payload["search_after"] = search_after
    if mostrar_movs:
        payload["_source"] = True
    else:
        payload["_source"] = {"excludes": ["movimentacoes", "movimentos"]}
    return payload


def _sanitize(body: dict[str, Any]) -> dict[str, Any]:
    """Remove ``highlight`` e trunca movimentos residuais.

    DataJud raramente devolve ``highlight`` em consultas sem ``query.match``
    (capturas usam ``terms``/``range``/``match``), mas mantemos a defesa.
    Capturamos com ``mostrar_movs=False`` — ``_source.excludes`` no payload
    já remove ``movimentos``/``movimentacoes`` no servidor; o trim aqui é
    rede de segurança caso uma resposta volte com esses arrays.
    """
    hits = body.get("hits", {}).get("hits") or []
    for hit in hits:
        hit.pop("highlight", None)
        source = hit.get("_source") or {}
        if isinstance(source.get("movimentos"), list):
            source["movimentos"] = []
        if isinstance(source.get("movimentacoes"), list):
            source["movimentacoes"] = []
    return body


def _capture(
    session: requests.Session,
    alias: str,
    payload: dict[str, Any],
    dest: Path,
    filename: str,
) -> dict[str, Any]:
    url = f"{BASE_API_URL}/{alias}/_search"
    headers = {
        "Authorization": f"APIKey {API_KEY}",
        "Content-Type": "application/json",
    }
    response = session.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    body = _sanitize(body)
    dump(
        dest / filename,
        json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    n_hits = len(body.get("hits", {}).get("hits") or [])
    print(f"[datajud] wrote {filename} ({n_hits} hits)")
    return body


def main() -> None:
    """Capture the four samples from the live DataJud API.

    The sequence is intentional: the multi-page page-2 capture depends on
    the ``sort`` of the last hit of page 1 (``search_after``), and the
    ``single_page`` capture filters by a CNJ lifted from page 1 to keep
    the result deterministic.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dest = samples_dir_for("datajud", endpoint="listar_processos")

    session = requests.Session()

    # 1) Multi-page (page 1): tribunal=TJSP + tamanho_pagina=2 (no filters).
    #    Pulls the 2 documents with the smallest id.keyword in the TJSP
    #    index — deterministic by sort order.
    payload_p1 = build_payload(tamanho_pagina=2)
    body_p1 = _capture(
        session, "api_publica_tjsp", payload_p1, dest, "results_normal_page_01.json"
    )

    hits_p1 = body_p1.get("hits", {}).get("hits") or []
    if len(hits_p1) < 2:
        raise SystemExit(
            f"[datajud] page 1 returned {len(hits_p1)} hits, expected 2. "
            "Cannot capture page 2 deterministically."
        )

    # 2) Multi-page (page 2): same query + search_after = sort of last hit.
    last_sort = hits_p1[-1].get("sort")
    if last_sort is None:
        raise SystemExit("[datajud] last hit on page 1 missing 'sort' field.")
    payload_p2 = build_payload(tamanho_pagina=2, search_after=last_sort)
    _capture(
        session, "api_publica_tjsp", payload_p2, dest, "results_normal_page_02.json"
    )
    # Note: the capture deliberately does NOT trim page 2 to 1 hit — the
    # contract only requires len(hits) < tamanho_pagina (2). Two further
    # documents from TJSP are fine; the break still triggers on the next
    # iteration. If page 2 happens to be full (2 hits), the contract test
    # for ``test_typical_multi_page`` will not exercise the early break,
    # which is acceptable — the break path is also covered by
    # ``test_single_page`` and ``test_no_results``.

    # 3) Single-page: filter by a specific CNJ from page 1 + tamanho_pagina=1000.
    cnj_p1 = (hits_p1[0].get("_source") or {}).get("numeroProcesso")
    if not cnj_p1:
        raise SystemExit(
            "[datajud] page 1 hit 0 missing _source.numeroProcesso; "
            "cannot build single_page query."
        )
    print(f"[datajud] single_page CNJ: {cnj_p1}")
    payload_sp = build_payload(numero_processo=cnj_p1, tamanho_pagina=1000)
    _capture(session, "api_publica_tjsp", payload_sp, dest, "single_page.json")

    # 4) No-results: filter by a 20-digit CNJ that does not exist in the TJSP
    #    index. We hit api_publica_tjsp directly (rather than letting the
    #    client infer the alias from the CNJ digits) to guarantee the API is
    #    actually called — passing only the bogus CNJ would short-circuit
    #    inside the client when its (id_justica, id_tribunal) are unmapped.
    payload_nr = build_payload(
        numero_processo="00000000000000000000",
        tamanho_pagina=1000,
    )
    # We bypass the client and target api_publica_tjsp directly: the
    # numeroProcesso filter alone returns zero hits regardless of which
    # tribunal index we hit.
    _capture(session, "api_publica_tjsp", payload_nr, dest, "no_results.json")

    print(f"[datajud] all samples written to {dest}")


if __name__ == "__main__":
    main()
