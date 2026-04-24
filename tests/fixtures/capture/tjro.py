"""Capture cjsg samples for TJRO.

Run from repo root::

    python -m tests.fixtures.capture.tjro

Saves raw JSON responses (Elasticsearch) under
``tests/tjro/samples/cjsg/``. Paginates via ``from`` offset — each
user-facing page is ``(p-1)*RESULTS_PER_PAGE``.
"""
import json

import requests

from juscraper.courts.tjro.download import BASE_URL, RESULTS_PER_PAGE, build_cjsg_payload

from ._util import dump, samples_dir_for

# Heavy field on each hit: truncate HTML blob to keep samples small.
_HIT_TRUNCATE = {"ds_modelo_documento": 500}


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
        # Drop highlight duplicates: parser doesn't read them.
        hit.pop("highlight", None)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _capture(session: requests.Session, dest, pesquisa: str, pagina_1based: int, filename: str) -> None:
    offset = (pagina_1based - 1) * RESULTS_PER_PAGE
    payload = build_cjsg_payload(pesquisa, offset=offset)
    response = session.post(BASE_URL, json=payload, timeout=30)
    response.raise_for_status()
    dump(dest / filename, _minify(response.content))
    print(f"[tjro] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJRO."""
    dest = samples_dir_for("tjro", "cjsg")
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
