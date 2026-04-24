"""Capture cjsg samples for TJSC.

Run from repo root::

    python -m tests.fixtures.capture.tjsc

Saves raw HTML responses (eproc) under ``tests/tjsc/samples/cjsg/``.
TJSC is dual-URL: page 1 hits ``listar_resultados``; page 2+ hit
``ajax_paginar_resultado``. The script exercises both.
"""
import requests

from juscraper.courts.tjsc.download import build_cjsg_form_body, cjsg_url_for_page

from ._util import dump, samples_dir_for


def _capture(session: requests.Session, dest, pesquisa: str, pagina_1based: int, filename: str) -> None:
    body = build_cjsg_form_body(pesquisa, page=pagina_1based)
    url = cjsg_url_for_page(pagina_1based)
    response = session.post(url, data=body, timeout=60)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    # eproc serves latin-1 pages — persist raw bytes so tests can load via
    # ``load_sample_bytes`` and the parser decodes with its own encoding rule.
    dump(dest / filename, response.content)
    print(f"[tjsc] wrote {filename} (page={pagina_1based}, url={url.split('@')[-1]})")


def main() -> None:
    """Capture cjsg HTML samples for TJSC."""
    dest = samples_dir_for("tjsc", "cjsg")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
    })

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.html")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.html")
    _capture(session, dest, "plano saude paciente doenca rara", 1, "single_page.html")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.html")


if __name__ == "__main__":
    main()
