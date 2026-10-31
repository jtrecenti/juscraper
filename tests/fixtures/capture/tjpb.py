"""Capture cjsg samples for TJPB.

Run from repo root::

    python -m tests.fixtures.capture.tjpb

Saves raw JSON responses (Laravel + Elasticsearch) under
``tests/tjpb/samples/cjsg/``. Heavy ``inteiro_teor`` blobs on each hit are
truncated — the parser only needs ementa/numero_processo/dt_ementa.
"""
import json
from urllib.parse import unquote

import requests

from juscraper.courts.tjpb.download import CLASSES_URL, SEARCH_URL, build_cjsg_payload

from ._util import dump, samples_dir_for

_HIT_TRUNCATE = {"inteiro_teor": 500, "ementa": 1500}


def _truncate(val, max_len: int):
    if isinstance(val, str) and len(val) > max_len:
        return val[:max_len] + "..."
    return val


def _minify(raw: bytes) -> bytes:
    data = json.loads(raw)
    for hit in data.get("hits", []) or []:
        for field, max_len in _HIT_TRUNCATE.items():
            if field in hit:
                hit[field] = _truncate(hit[field], max_len)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _capture(session: requests.Session, dest, xsrf_token: str, pesquisa: str,
             page: int, filename: str) -> None:
    payload = build_cjsg_payload(pesquisa=pesquisa, page=page)
    response = session.post(
        SEARCH_URL,
        json=payload,
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": xsrf_token,
        },
        timeout=60,
    )
    response.raise_for_status()
    dump(dest / filename, _minify(response.content))
    print(f"[tjpb] wrote {filename} (page={page}, bytes={len(response.content)})")


def main() -> None:
    """Capture cjsg JSON samples for TJPB."""
    dest = samples_dir_for("tjpb", "cjsg")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
    })

    classes_resp = session.get(CLASSES_URL, timeout=30)
    classes_resp.raise_for_status()
    xsrf_cookie = session.cookies.get("XSRF-TOKEN")
    if not xsrf_cookie:
        raise RuntimeError("TJPB did not provide the XSRF-TOKEN cookie.")
    xsrf_token = unquote(xsrf_cookie)

    _capture(session, dest, xsrf_token, "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, xsrf_token, "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, xsrf_token, "usucapiao extraordinario imovel rural",
             1, "single_page.json")
    _capture(session, dest, xsrf_token, "juscraper_probe_zero_hits_xyzqwe",
             1, "no_results.json")


if __name__ == "__main__":
    main()
