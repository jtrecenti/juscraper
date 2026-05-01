"""Capture cjsg samples for TJRR.

Run from repo root::

    python -m tests.fixtures.capture.tjrr

Saves raw HTML/XML responses under ``tests/tjrr/samples/cjsg/``. TJRR's
flow is JSF/PrimeFaces-based and *every* request hits the same URL
(``/index.xhtml``); requests are differentiated by HTTP method and body
shape:

- ``step_01_consulta.html`` — initial GET (extracts ``ViewState`` and the
  dynamic component IDs the JSF backend renders for the search form).
- ``step_02_search.html`` — POST with the form-urlencoded body that
  carries the search ``pesquisa`` and ``ViewState`` (returns HTML with
  page 1 results inline).
- ``step_03_pagina_02.xml`` — partial-response POST with
  ``javax.faces.partial.ajax=true`` that pages forward; the response is
  XML wrapping the result HTML inside a ``<![CDATA[...]]>`` block.
- ``single_page.html`` — POST whose hits fit on one page (no AJAX
  follow-up).
- ``no_results.html`` — POST that yields zero hits.

The capture installs a response hook on the scraper's ``Session`` and
classifies each response by ``method`` + ``scenario`` + body content.
Samples are byte-identical to what the live backend served.
"""
from __future__ import annotations

from typing import Optional

import juscraper as jus

from ._util import samples_dir_for


def _classify(
    method: str,
    body_text: str,
    scenario: str,
    counters: dict[str, int],
) -> Optional[str]:
    """Pick the filename for a given response, or ``None`` to skip."""
    if method == "GET":
        return "step_01_consulta.html"

    if method != "POST":
        return None

    is_ajax = "javax.faces.partial.ajax=true" in body_text
    if is_ajax:
        # Each AJAX call advances the page by one; the first AJAX = page 2.
        counters["ajax"] = counters.get("ajax", 0) + 1
        page_num = counters["ajax"] + 1  # AJAX kicks in for pages 2+.
        step_num = counters["ajax"] + 2  # GET=01, POST inicial=02, AJAX=03+
        if scenario == "typical":
            return f"step_{step_num:02d}_pagina_{page_num:02d}.xml"  # noqa: E231
        # AJAX in non-typical scenarios is unexpected (paginas=1).
        return None

    # Initial POST.
    if scenario == "typical":
        return "step_02_search.html"
    return f"{scenario}.html"


def main() -> None:
    """Capture cjsg HTML/XML samples for TJRR."""
    dest = samples_dir_for("tjrr", "cjsg")
    scraper = jus.scraper("tjrr")

    state: dict = {"scenario": None}
    seen_files: set[str] = set()
    counters: dict[str, int] = {}

    def hook(resp, *args, **kwargs):
        scenario = state.get("scenario")
        if scenario is None:
            return resp
        method = (resp.request.method or "GET").upper()
        body = resp.request.body or b""
        if isinstance(body, bytes):
            try:
                body_text = body.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - best-effort decode
                body_text = ""
        else:
            body_text = str(body)
        filename = _classify(method, body_text, scenario, counters)
        if filename and filename not in seen_files:
            (dest / filename).write_bytes(resp.content)
            print(f"[tjrr/{scenario}] -> {filename}")
            seen_files.add(filename)
        return resp

    def _install_hook():
        scraper.session.hooks["response"].append(hook)

    def _reset_session():
        """Recreate the session and reinstall the hook.

        TJRR's JSF backend retains state across requests in a single
        session (cookies + server-side ``ViewState`` cache); switching
        scenarios on the same session can leak filter state — most
        notably, the date filter for ``no_results`` was being silently
        ignored after a ``single_page`` search ran first.
        """
        import requests
        scraper.session = requests.Session()
        scraper.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })
        _install_hook()

    _install_hook()

    # Typical: 2-page pagination (GET + POST initial + 1 AJAX).
    state["scenario"] = "typical"
    counters.clear()
    df = scraper.cjsg("dano moral", paginas=range(1, 3))
    print(f"[tjrr/typical] DataFrame columns: {list(df.columns)}")
    print(f"[tjrr/typical] rows: {len(df)}")

    # Single page: query whose hits fit in one page.
    _reset_session()
    state["scenario"] = "single_page"
    counters.clear()
    df = scraper.cjsg("usucapiao", paginas=1)
    print(f"[tjrr/single_page] rows: {len(df)}")

    # Zero hits. Two TJRR quirks make this tricky: (1) common terms
    # (e.g. "dano moral") bypass the date filter and return the default
    # catalogue; (2) unknown terms alone fall back to "all acórdãos"
    # without respecting the search either. Combining an improbable
    # term *and* an impossible future date range is what reliably
    # yields an empty result set — but only on a fresh session
    # (see ``_reset_session`` above).
    _reset_session()
    state["scenario"] = "no_results"
    counters.clear()
    df = scraper.cjsg(
        "juscraperprobeztzeroxyz",
        paginas=1,
        data_julgamento_inicio="01/01/2099",
        data_julgamento_fim="31/12/2099",
    )
    print(f"[tjrr/no_results] rows: {len(df)} (expected 0)")


if __name__ == "__main__":
    main()
