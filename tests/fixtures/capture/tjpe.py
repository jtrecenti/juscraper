"""Capture cjsg samples for TJPE.

Run from repo root::

    python -m tests.fixtures.capture.tjpe

Saves raw HTML/XML responses under ``tests/tjpe/samples/cjsg/``. TJPE's
flow is JSF/RichFaces-based and spans **three different XHTML endpoints**
under ``/consultajurisprudenciaweb/xhtml/consulta/``:

- ``consulta.xhtml`` — initial GET (extracts ``ViewState``) and search POST.
  When the user picks ``tipo_decisao="todos"`` the POST returns the
  *escolha* page (a chooser between Acordaos and Decisoes Monocraticas).
  When a single ``tipo_decisao`` is selected, the POST returns the
  results page directly.
- ``escolhaResultado.xhtml`` — POST that picks one of the result types
  and returns the first results page (only used when escolha is shown).
- ``resultado.xhtml`` — AJAX POST (``AJAXREQUEST=_viewRoot``) that paginates
  to page N. The response is RichFaces XML wrapping the result HTML inside
  a ``<![CDATA[...]]>`` block.

Three scenarios per the umbrella issue (#197):

- **escolha** — 4 chamadas (GET + POST consulta=escolha + POST escolha
  + AJAX page 2). Files: ``step_01_consulta.html``, ``step_02_escolha.html``,
  ``step_03_resultado.html``, ``step_04_pagina_02.xml``.
- **simples** — 3 chamadas (GET + POST consulta=results + AJAX page 2).
  Files (reusam ``step_01_consulta.html`` do escolha):
  ``simples_resultado.html``, ``simples_pagina_02.xml``.
- **no_results** — 2 chamadas (GET + POST consulta com 0 docs). File:
  ``no_results.html``.

The capture installs a response hook on the scraper's ``Session`` and
classifies each response by URL path + HTTP method + scenario. Samples are
byte-identical to what the live backend served.
"""
from __future__ import annotations

from urllib.parse import urlparse

import requests

import juscraper as jus

from ._util import samples_dir_for


def _classify(
    method: str,
    url: str,
    scenario: str,
    counters: dict[str, int],
) -> str | None:
    """Pick the filename for a given response, or ``None`` to skip."""
    path = urlparse(url).path.rsplit("/", 1)[-1]

    if scenario == "escolha":
        if method == "GET" and path == "consulta.xhtml":
            return "step_01_consulta.html"
        if method == "POST" and path == "consulta.xhtml":
            return "step_02_escolha.html"
        if method == "POST" and path == "escolhaResultado.xhtml":
            return "step_03_resultado.html"
        if method == "POST" and path == "resultado.xhtml":
            counters["ajax"] = counters.get("ajax", 0) + 1
            page_num = counters["ajax"] + 1  # AJAX kicks in for pages 2+
            step_num = counters["ajax"] + 3  # GET=01, POST=02, escolha=03, AJAX=04+
            return f"step_{step_num:02d}_pagina_{page_num:02d}.xml"  # noqa: E231
        return None

    if scenario == "simples":
        if method == "GET" and path == "consulta.xhtml":
            # Already captured under escolha; skip to avoid clobbering.
            return None
        if method == "POST" and path == "consulta.xhtml":
            return "simples_resultado.html"
        if method == "POST" and path == "resultado.xhtml":
            counters["ajax"] = counters.get("ajax", 0) + 1
            page_num = counters["ajax"] + 1
            return f"simples_pagina_{page_num:02d}.xml"  # noqa: E231
        return None

    if scenario == "no_results":
        if method == "GET" and path == "consulta.xhtml":
            # Reuse step_01_consulta.html captured under escolha.
            return None
        if method == "POST" and path == "consulta.xhtml":
            return "no_results.html"
        return None

    return None


def main() -> None:
    """Capture cjsg HTML/XML samples for TJPE."""
    dest = samples_dir_for("tjpe", "cjsg")
    scraper = jus.scraper("tjpe")

    state: dict = {"scenario": None}
    seen_files: set[str] = set()
    counters: dict[str, int] = {}

    def hook(resp, *args, **kwargs):
        scenario = state.get("scenario")
        if scenario is None:
            return resp
        method = (resp.request.method or "GET").upper()
        url = resp.request.url or ""
        filename = _classify(method, url, scenario, counters)
        if filename and filename not in seen_files:
            (dest / filename).write_bytes(resp.content)
            print(f"[tjpe/{scenario}] -> {filename} ({len(resp.content)} bytes)")
            seen_files.add(filename)
        return resp

    def _install_hook():
        scraper.session.hooks["response"].append(hook)

    def _reset_session():
        """Recreate the session and reinstall the hook.

        TJPE's JSF backend keeps server-side ViewState tied to the
        JSESSIONID cookie. Reusing a session across scenarios can carry
        forward filter state (notably the ``tipoDecisao`` checkboxes
        between escolha and simples) and corrupt the captured payloads.
        """
        scraper.session = requests.Session()
        scraper.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })
        _install_hook()

    _install_hook()

    # 1) escolha: tipo_decisao="todos" forces the chooser page (4 calls).
    state["scenario"] = "escolha"
    counters.clear()
    df = scraper.cjsg("dano moral", paginas=range(1, 3), tipo_decisao="todos")
    print(f"[tjpe/escolha] DataFrame columns: {list(df.columns)}")
    print(f"[tjpe/escolha] rows: {len(df)}")

    # 2) simples: default tipo_decisao="acordaos" skips the chooser (3 calls).
    _reset_session()
    state["scenario"] = "simples"
    counters.clear()
    df = scraper.cjsg("dano moral", paginas=range(1, 3))
    print(f"[tjpe/simples] rows: {len(df)}")

    # 3) no_results: improbable term yields 0 documents (2 calls; AJAX skipped).
    _reset_session()
    state["scenario"] = "no_results"
    counters.clear()
    df = scraper.cjsg("juscraperprobeztzeroxyz", paginas=1)
    print(f"[tjpe/no_results] rows: {len(df)} (expected 0)")


if __name__ == "__main__":
    main()
