"""Capture cjsg samples for TJDFT.

Run from repo root::

    python -m tests.fixtures.capture.tjdft
"""
import requests

from juscraper.courts.tjdft.download import BASE_URL, build_cjsg_payload

from ._util import dump, samples_dir_for


def _capture(session: requests.Session, dest, pesquisa: str, pagina: int, filename: str) -> None:
    # ``pagina`` é 1-based, como em ``cjsg``; a API conta a partir de 0.
    response = session.post(BASE_URL, json=build_cjsg_payload(pesquisa, pagina - 1), timeout=30)
    response.raise_for_status()
    dump(dest / filename, response.content)
    print(f"[tjdft] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJDFT."""
    dest = samples_dir_for("tjdft", "cjsg")
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, "mandado de seguranca", 1, "single_page.json")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json")
    # Busca com 13 acórdãos (2 páginas) para o ``paginas=None``.
    _capture(session, dest, "enfiteuse", 1, "todas_paginas_page_01.json")
    _capture(session, dest, "enfiteuse", 2, "todas_paginas_page_02.json")


if __name__ == "__main__":
    main()
