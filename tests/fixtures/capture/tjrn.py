"""Capture cjsg samples for TJRN.

Run from repo root::

    python -m tests.fixtures.capture.tjrn

Saves raw JSON responses (Elasticsearch) under
``tests/tjrn/samples/cjsg/``. Truncates long ``inteiro_teor`` blobs
on each hit; the contract parser only reads ementa/metadados and the
full documento stays behind a separate endpoint.
"""
import json

import requests

from juscraper.courts.tjrn.download import BASE_URL, build_cjsg_payload

from ._util import dump, samples_dir_for

# Heavy fields on each hit: truncate to keep samples small while preserving
# structure. The parser in ``courts/tjrn/parse.py`` consumes ``ementa`` (via
# ``inteiro_teor``) but we don't need multi-KB HTML blobs for contract tests.
_HIT_TRUNCATE = {"inteiro_teor": 500}


def _truncate(val, max_len: int):
    if isinstance(val, str) and len(val) > max_len:
        return val[:max_len] + "..."
    return val


def _minify(raw: bytes) -> bytes:
    data = json.loads(raw)
    for hit in data.get("hits", {}).get("hits", []) or []:
        src = hit.get("_source", {}) or {}
        for field, max_len in _HIT_TRUNCATE.items():
            if field in src:
                src[field] = _truncate(src[field], max_len)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _capture(session: requests.Session, dest, pesquisa: str, pagina: int, filename: str) -> None:
    payload = build_cjsg_payload(pesquisa, page=pagina)
    response = session.post(BASE_URL, json=payload, timeout=30)
    response.raise_for_status()
    dump(dest / filename, _minify(response.content))
    print(f"[tjrn] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJRN."""
    dest = samples_dir_for("tjrn", "cjsg")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
    })

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, "mandado de seguranca", 1, "single_page.json")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json")


if __name__ == "__main__":
    main()
