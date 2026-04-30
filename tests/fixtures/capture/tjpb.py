"""Capture cjsg samples for TJPB.

Run from repo root::

    python -m tests.fixtures.capture.tjpb

Saves raw JSON responses (Laravel + Elasticsearch) under
``tests/tjpb/samples/cjsg/`` plus the home page that carries the
``_token`` CSRF meta tag. Heavy ``inteiro_teor`` blobs on each hit are
truncated — the parser only needs ementa/numero_processo/dt_ementa.
"""
import json

import requests

from juscraper.courts.tjpb.download import BASE_URL, SEARCH_URL, build_cjsg_payload, fetch_csrf_token

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


def _capture(session: requests.Session, dest, token: str, pesquisa: str,
             page: int, filename: str) -> None:
    payload = build_cjsg_payload(token=token, pesquisa=pesquisa, page=page)
    response = session.post(
        SEARCH_URL,
        json=payload,
        headers={"X-Requested-With": "XMLHttpRequest"},
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

    home_resp = session.get(BASE_URL, timeout=30)
    home_resp.raise_for_status()
    dump(dest / "home.html", home_resp.content)
    print(f"[tjpb] wrote home.html (bytes={len(home_resp.content)})")

    token = fetch_csrf_token(session)

    _capture(session, dest, token, "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, token, "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, token, "usucapiao extraordinario imovel rural",
             1, "single_page.json")
    _capture(session, dest, token, "juscraper_probe_zero_hits_xyzqwe",
             1, "no_results.json")


if __name__ == "__main__":
    main()
