"""Capture cjsg samples for TJAP.

Run from repo root::

    python -m tests.fixtures.capture.tjap
"""
import json

import requests

from juscraper.courts.tjap.download import BASE_URL, FRONT_URL, RESULTS_PER_PAGE, _build_payload

from ._util import dump, samples_dir_for


def _capture(session: requests.Session, dest, pesquisa: str, pagina: int, filename: str) -> None:
    offset = (pagina - 1) * RESULTS_PER_PAGE
    payload = _build_payload(pesquisa, offset=offset)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    response = session.post(
        BASE_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": FRONT_URL,
            "tucujuris-front-url": FRONT_URL,
        },
        timeout=30,
    )
    response.raise_for_status()
    dump(dest / filename, response.content)
    print(f"[tjap] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJAP."""
    dest = samples_dir_for("tjap", "cjsg")
    session = requests.Session()
    session.headers.update({"User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)"})

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, "mandado de seguranca", 1, "single_page.json")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json")


if __name__ == "__main__":
    main()
