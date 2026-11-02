"""Capture cjsg samples for TJRJ.

Run from repo root::

    python -m tests.fixtures.capture.tjrj

Saves the live form HTML (with fresh ``__VIEWSTATE``) and the JSON XHR
payloads under ``tests/tjrj/samples/cjsg/``. The TJRJ flow has three
steps: (1) ``GET`` the form to extract hidden fields, (2) ``POST`` the
form to seed the server-side session, (3) ``POST`` the JSON XHR per page.
The contract test mocks all three. When ``origem`` differs from the form
default, step (2) is preceded by the ``cmbOrigem`` postback, whose HTML is
also saved.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import requests

from juscraper.courts.tjrj.download import FORM_URL, RESULT_URL, build_cjsg_payload, extract_viewstate_fields

from ._util import dump, samples_dir_for

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def _seed_session(
    session: requests.Session, pesquisa: str, ano: str, origem: str = "1",
) -> tuple[bytes, bytes | None, str]:
    """Run GET + POST and return the GET HTML, the origin postback HTML and the PageSeq.

    ``ano`` is required: in 2026-04-30 the TJRJ backend started returning
    a 500 on ``cmbAnoInicio``/``cmbAnoFim`` empty (refs #143). Captures
    always pin a year so they match the contract test fixtures.
    """
    get_resp = session.get(FORM_URL, timeout=30)
    get_resp.raise_for_status()
    body = build_cjsg_payload(
        hidden=extract_viewstate_fields(get_resp.text), pesquisa=pesquisa,
        ano_inicio=ano, ano_fim=ano, origem=origem,
    )
    postback_html = None
    if origem != "1":
        postback = dict(body, __EVENTTARGET="ctl00$ContentPlaceHolder1$cmbOrigem")
        postback_resp = session.post(FORM_URL, data=postback, timeout=30)
        postback_resp.raise_for_status()
        postback_html = postback_resp.content
        body.update(extract_viewstate_fields(postback_resp.text))
    post_resp = session.post(FORM_URL, data=body, timeout=30, allow_redirects=True)
    post_resp.raise_for_status()
    page_seq = parse_qs(urlparse(post_resp.url).query)["PageSeq"][0]
    print(f"[tjrj] form redirect: {post_resp.history[0].headers.get('Location')}")
    return get_resp.content, postback_html, page_seq


def _fetch_xhr(session: requests.Session, num_pagina_0: int, page_seq: str) -> dict:
    payload = {"numPagina": num_pagina_0, "pageSeq": page_seq}
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
    origem: str = "1",
    postback_file: str | None = None,
) -> None:
    form_html, postback_html, page_seq = _seed_session(session, pesquisa, ano, origem)
    if save_form:
        dump(dest / "post_initial.html", form_html)
        print(f"[tjrj] form HTML for '{pesquisa}' saved (bytes={len(form_html)})")
    if postback_file and postback_html is not None:
        dump(dest / postback_file, postback_html)
        print(f"[tjrj] origem={origem} postback HTML saved (bytes={len(postback_html)})")
    for num_pagina_0, filename in page_files.items():
        payload = _fetch_xhr(session, num_pagina_0, page_seq)
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

    capture_turma_recursal(dest)

    print(f"[tjrj] ALL samples written to {dest}")


def capture_turma_recursal(dest) -> None:
    """Turma Recursal (``origem="4"``): the form needs the ``cmbOrigem`` postback."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    _capture_query(
        session,
        dest,
        "cancelamento de voo",
        ano="2025",
        save_form=False,
        page_files={0: "xhr_turma_recursal.json"},
        origem="4",
        postback_file="postback_origem_turma_recursal.html",
    )


if __name__ == "__main__":
    main()
