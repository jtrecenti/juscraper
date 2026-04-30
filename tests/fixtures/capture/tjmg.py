"""Capture cjsg samples for TJMG.

Run from repo root::

    pip install txtcaptcha    # required for live captcha decoding
    python -m tests.fixtures.capture.tjmg

Saves raw responses for the four endpoints TJMG hits per ``cjsg`` call:

- ``form_acordao.html`` — GET ``formEspelhoAcordao.do`` (initial form).
- ``captcha.png`` — GET ``captcha.svl`` (5-digit numeric captcha image).
- ``dwr_validate.txt`` — POST DWR plaintext validating the decoded
  captcha (server flags the session as captcha-validated; subsequent
  searches in the same session reuse the flag).
- ``results_normal_page_NN.html`` — typical multi-page scenario.
- ``single_page.html`` — single-page scenario.
- ``no_results.html`` — zero-hit scenario.

The PNG sample stored is the *real* captcha bytes captured live (per the
project rule "samples sempre do backend real"). Decoding inside pytest
is mocked out — the pytest contract patches ``txtcaptcha`` into
``sys.modules`` with a stub. Capture, however, runs against the real
backend and needs the real ``txtcaptcha`` installed locally; it is **not**
listed in ``pyproject.toml`` because runtime users of the library don't
need it unless they use TJMG.
"""
from __future__ import annotations

from typing import Optional

import juscraper as jus

from ._util import samples_dir_for


def _classify(
    url: str,
    method: str,
    scenario: str,
    counters: dict[str, int],
) -> Optional[str]:
    """Pick the filename for a given response, or ``None`` to skip."""
    if "formEspelhoAcordao.do" in url:
        return "form_acordao.html"
    if "captcha.svl" in url:
        return "captcha.png"
    if ".dwr" in url and method == "POST":
        return "dwr_validate.txt"
    if "pesquisaPalavrasEspelhoAcordao.do" in url:
        if scenario == "typical":
            counters["search"] = counters.get("search", 0) + 1
            return f"results_normal_page_{counters['search']:02d}.html"  # noqa: E231
        return f"{scenario}.html"
    return None


def main() -> None:
    """Capture cjsg samples for TJMG."""
    dest = samples_dir_for("tjmg", "cjsg")
    scraper = jus.scraper("tjmg")

    state: dict = {"scenario": None}
    seen_files: set[str] = set()
    counters: dict[str, int] = {}

    def hook(resp, *args, **kwargs):
        scenario = state.get("scenario")
        if scenario is None:
            return resp
        method = (resp.request.method or "GET").upper()
        filename = _classify(resp.url, method, scenario, counters)
        if filename and filename not in seen_files:
            (dest / filename).write_bytes(resp.content)
            print(f"[tjmg/{scenario}] -> {filename}")
            seen_files.add(filename)
        return resp

    scraper.session.hooks["response"].append(hook)

    # Typical: 2-page pagination, with date filter to avoid the
    # "muitos resultados" cap (TJMG rejects >400 hits).
    state["scenario"] = "typical"
    counters.clear()
    df = scraper.cjsg(
        "dano moral",
        paginas=range(1, 3),
        data_julgamento_inicio="01/01/2025",
        data_julgamento_fim="31/01/2025",
    )
    print(f"[tjmg/typical] DataFrame columns: {list(df.columns)}")
    print(f"[tjmg/typical] rows: {len(df)}")

    # Single page: a narrower phrase whose hits fit in one page (the
    # date filter is unreliable here — TJMG silently returns 0 for
    # most narrow date windows even on common terms).
    state["scenario"] = "single_page"
    counters.clear()
    df = scraper.cjsg(
        "homicidio qualificado dolo eventual",
        paginas=1,
    )
    print(f"[tjmg/single_page] rows: {len(df)}")

    # Zero hits.
    state["scenario"] = "no_results"
    counters.clear()
    df = scraper.cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)
    print(f"[tjmg/no_results] rows: {len(df)} (expected 0)")


if __name__ == "__main__":
    main()
