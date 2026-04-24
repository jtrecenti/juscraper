"""Capture cjsg samples for TJPA.

Run from repo root::

    python -m tests.fixtures.capture.tjpa

Saves raw JSON responses (BFF) under ``tests/tjpa/samples/cjsg/``.
The BFF paginates 0-based server-side — passing user-facing page 1
means we send ``page=0`` in the body. Post-processes each response
to drop ``facets``/``consultaUtilizada`` at the top level and the
heavy ``textooriginal``/``textopuro``/``*Highlight`` fields per hit
(parser only reads ``ementatextopuro``). Keeps samples under ~200 KB.
"""
import json

import requests

from juscraper.courts.tjpa.download import BASE_URL, CJSG_HEADERS, build_cjsg_payload

from ._util import dump, samples_dir_for

# Top-level keys the parser ignores under ``data``; drop from samples.
_DATA_DROP = {"facets", "consultaUtilizada"}

# Per-hit heavy fields: drop entirely (parser reads only ``ementatextopuro``
# and a handful of metadata fields documented in ``tjpa/parse.py``).
_HIT_DROP = {
    "textooriginal",
    "textopuro",
    "textoementa",
    "textopuroHighlight",
    "ementatextopuroHighlight",
    "binario",
}


def _minify(raw: bytes) -> bytes:
    data = json.loads(raw)
    payload = data.get("data")
    if isinstance(payload, dict):
        for key in _DATA_DROP:
            payload.pop(key, None)
        for hit in payload.get("content", []) or []:
            for field in _HIT_DROP:
                hit.pop(field, None)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _capture(session: requests.Session, dest, pesquisa: str, pagina_1based: int, filename: str) -> None:
    payload = build_cjsg_payload(pesquisa, pagina_0based=pagina_1based - 1)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    response = session.post(BASE_URL, data=body, headers=CJSG_HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    dump(dest / filename, _minify(response.content))
    print(f"[tjpa] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJPA."""
    dest = samples_dir_for("tjpa", "cjsg")
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
