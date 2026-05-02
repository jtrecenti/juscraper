"""Capture cjsg samples for TJPR.

Run from repo root::

    python -m tests.fixtures.capture.tjpr

Saves raw HTML responses under ``tests/tjpr/samples/cjsg/``. TJPR's flow
involves a GET home (extracts JSESSIONID + ``tjpr.url.crypto`` token),
POST per page, and an extra GET per row that contains "Leia mais..."
(``actionType=exibirTextoCompleto``).

The capture installs a response hook on the scraper's ``Session`` that
classifies each response by URL/scenario. Files produced:

- ``home.html`` — landing page (shared; the scraper hits it twice per
  ``cjsg`` call, once during download and once during parse).
- ``results_normal_page_NN.html`` — one per POST in the ``typical``
  scenario (multi-page pagination).
- ``single_page.html`` — single POST whose results fit on one page.
- ``no_results.html`` — single POST with zero hits.
- ``ementa_completa.html`` — single sample for the GET extras. As of
  2026-04, the upstream endpoint returns a generic Struts error page
  (``NoSuchMethodException``) regardless of ``idProcesso``/``criterio``,
  so all responses are byte-identical and we keep just one. The
  contract test reuses this sample for all "Leia mais..." calls.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import juscraper as jus

from ._util import samples_dir_for


def _classify(url: str, kind: str, scenario: str, page_counter: dict[str, int]) -> str | None:
    """Pick the filename to use for the given response, or ``None`` to skip."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    action = (params.get("actionType") or [""])[0]

    if kind == "GET" and not action:
        return "home.html"

    if kind == "GET" and action == "exibirTextoCompleto":
        return "ementa_completa.html"

    if kind == "POST":
        if scenario == "typical":
            page_counter[scenario] = page_counter.get(scenario, 0) + 1
            return f"results_normal_page_{page_counter[scenario]:02d}.html"
        return f"{scenario}.html"

    return None


def main() -> None:
    """Capture cjsg HTML samples for TJPR."""
    dest = samples_dir_for("tjpr", "cjsg")
    scraper = jus.scraper("tjpr")

    state: dict = {"scenario": None}
    page_counter: dict[str, int] = {}
    seen_files: set[str] = set()

    def hook(resp, *args, **kwargs):
        scenario = state.get("scenario")
        if scenario is None:
            return resp
        kind = resp.request.method or "GET"
        filename = _classify(resp.url, kind, scenario, page_counter)
        if filename and filename not in seen_files:
            (dest / filename).write_bytes(resp.content)
            print(f"[tjpr/{scenario}] -> {filename}")
            seen_files.add(filename)
        return resp

    scraper.session.hooks["response"].append(hook)

    # Typical: 2-page pagination + N "Leia mais..." GETs (we keep one).
    state["scenario"] = "typical"
    seen_files.clear()
    df = scraper.cjsg("dano moral", paginas=range(1, 3))
    print(f"[tjpr/typical] DataFrame columns: {list(df.columns)}")
    print(f"[tjpr/typical] rows: {len(df)}")

    # Single page: a query that yields ~one page worth of hits.
    state["scenario"] = "single_page"
    seen_files.clear()
    df = scraper.cjsg("direito civil", paginas=1)
    print(f"[tjpr/single_page] rows: {len(df)}")

    # Zero hits.
    state["scenario"] = "no_results"
    seen_files.clear()
    df = scraper.cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)
    print(f"[tjpr/no_results] rows: {len(df)} (expected 0)")


if __name__ == "__main__":
    main()
