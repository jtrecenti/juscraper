"""Capture cjsg samples for TJRJ.

Run from repo root::

    python -m tests.fixtures.capture.tjrj

Saves the live form HTML (with fresh ``__VIEWSTATE``) and the JSON XHR
payloads under ``tests/tjrj/samples/cjsg/``. The TJRJ flow has three
steps: (1) ``GET`` the form to extract hidden fields, (2) ``POST`` the
form to seed the server-side session, (3) ``POST`` the JSON XHR per page.
The contract test mocks all three.
"""
from __future__ import annotations

import json

import requests

from juscraper.courts.tjrj.download import FORM_URL, RESULT_URL, build_cjsg_payload, extract_viewstate_fields

from ._util import dump, samples_dir_for

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def _seed_session(session: requests.Session, pesquisa: str, ano: str) -> bytes:
    """Run GET + POST and return the GET HTML so the caller can dump it.

    ``ano`` is required: in 2026-04-30 the TJRJ backend started returning
    a 500 on ``cmbAnoInicio``/``cmbAnoFim`` empty (refs #143). Captures
    always pin a year so they match the contract test fixtures.
    """
    get_resp = session.get(FORM_URL, timeout=30)
    get_resp.raise_for_status()
    hidden = extract_viewstate_fields(get_resp.text)
    body = build_cjsg_payload(hidden=hidden, pesquisa=pesquisa, ano_inicio=ano, ano_fim=ano)
    post_resp = session.post(FORM_URL, data=body, timeout=30, allow_redirects=True)
    post_resp.raise_for_status()
    return get_resp.content


def _fetch_xhr(session: requests.Session, num_pagina_0: int) -> dict:
    payload = {"numPagina": num_pagina_0, "pageSeq": "0"}
    resp = session.post(
        RESULT_URL,
        json=payload,
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=60,
    )
    resp.raise_for_status()
    response_payload: dict = resp.json()
    return response_payload


def _capture_query(
    session: requests.Session,
    dest,
    pesquisa: str,
    *,
    ano: str,
    save_form: bool,
    page_files: dict[int, str],
) -> None:
    form_html = _seed_session(session, pesquisa, ano)
    if save_form:
        dump(dest / "post_initial.html", form_html)
        print(f"[tjrj] form HTML for '{pesquisa}' saved (bytes={len(form_html)})")
    for num_pagina_0, filename in page_files.items():
        payload = _fetch_xhr(session, num_pagina_0)
        dump(dest / filename, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        total = payload.get("d", {}).get("TotalDocs")
        print(f"[tjrj] '{pesquisa}' page={num_pagina_0} -> {filename} (TotalDocs={total})")


def main() -> None:
    """Capture cjsg samples for TJRJ."""
    dest = samples_dir_for("tjrj", "cjsg")

    typical_session = requests.Session()
    typical_session.headers.update({"User-Agent": USER_AGENT})
    _capture_query(
        typical_session,
        dest,
        "dano moral",
        ano="2024",
        save_form=True,
        page_files={0: "xhr_page_01.json", 1: "xhr_page_02.json"},
    )

    single_session = requests.Session()
    single_session.headers.update({"User-Agent": USER_AGENT})
    _capture_query(
        single_session,
        dest,
        "usucapiao extraordinario predio rural familia",
        ano="2024",
        save_form=False,
        page_files={0: "xhr_single_page.json"},
    )

    none_session = requests.Session()
    none_session.headers.update({"User-Agent": USER_AGENT})
    _capture_query(
        none_session,
        dest,
        "juscraper_probe_zero_hits_xyzqwe",
        ano="2024",
        save_form=False,
        page_files={0: "xhr_no_results.json"},
    )

    print(f"[tjrj] ALL samples written to {dest}")


if __name__ == "__main__":
    main()
