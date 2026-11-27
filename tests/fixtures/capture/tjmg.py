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
- ``erro_ora.html`` — search without a date filter: on 15/11/2026 the portal
  answered with ``ORA-20000 ... DRG-10599`` instead of results. On 26/11/2026
  the same search answered "muitos resultados"; the sample is only rewritten
  when the portal answers with the database error again.
- ``muitos_resultados.html`` — a common search with too many hits (11,170;
  1,905 are still listed): the portal answers "Sua pesquisa encontrou muitos
  resultados (N) e não pode ser exibida" instead of results.
- ``categorizada.html`` — "Resultado da busca (Categorizada)": with
  repetitive-appeal rulings among the hits, the portal lists only the count
  per category, with a link to each category's list.
- ``categorizada_repetitivos.html`` — the repetitive-appeal list
  (``listaClasse=600``) that ``cjsg_download`` follows from that page.
- ``categorizada_acordaos_page_NN.html`` — the other rulings
  (``excluirRepetitivos=true``), pages 1 and 2.

The PNG sample stored is the *real* captcha bytes captured live (per the
project rule "samples sempre do backend real"). Decoding inside pytest
is mocked out — the pytest contract patches ``txtcaptcha`` into
``sys.modules`` with a stub. Capture, however, runs against the real
backend and needs the real ``txtcaptcha`` installed locally; it is **not**
listed in ``pyproject.toml`` because runtime users of the library don't
need it unless they use TJMG.
"""
from __future__ import annotations

import juscraper as jus
from juscraper.courts.tjmg.parse import TJMGBuscaSemListaError

from ._util import samples_dir_for


def _classify(
    url: str,
    method: str,
    scenario: str,
    counters: dict[str, int],
) -> str | None:
    """Pick the filename for a given response, or ``None`` to skip."""
    if "formEspelhoAcordao.do" in url:
        return "form_acordao.html"
    if "captcha.svl" in url:
        return "captcha.png"
    if ".dwr" in url and method == "POST":
        return "dwr_validate.txt"
    if "pesquisaPalavrasEspelhoAcordao.do" in url:
        return _classify_search(url, scenario, counters)
    return None


def _classify_search(url: str, scenario: str, counters: dict[str, int]) -> str:
    """Filename of a search page; the categorized lists are told apart by their link parameter."""
    if "listaClasse=600" in url:
        return "categorizada_repetitivos.html"
    if "excluirRepetitivos=true" in url:
        counters["acordaos"] = counters.get("acordaos", 0) + 1
        return f"categorizada_acordaos_page_{counters['acordaos']:02d}.html"
    if scenario == "typical":
        counters["search"] = counters.get("search", 0) + 1
        return f"results_normal_page_{counters['search']:02d}.html"
    return f"{scenario}.html"


def main() -> None:
    """Capture cjsg samples for TJMG."""
    dest = samples_dir_for("tjmg", "cjsg")
    scraper = jus.scraper("tjmg")

    state: dict = {"scenario": None}
    seen_files: set[str] = set()
    counters: dict[str, int] = {}

    def hook(resp, *args, **kwargs):
        if "pesquisaPalavrasEspelhoAcordao.do" in resp.url:
            state["last_search"] = resp.content
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
    # "muitos resultados" cap (see ``muitos_resultados`` below).
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

    # Single page: a narrower phrase whose hits fit in one page. The date
    # filter keeps the hits stable (and on 15/11/2026, without it, the portal
    # answered with ORA-20000; see ``erro_ora``).
    state["scenario"] = "single_page"
    counters.clear()
    df = scraper.cjsg(
        "homicidio qualificado dolo eventual",
        paginas=1,
        data_julgamento_inicio="01/01/2025",
        data_julgamento_fim="31/01/2025",
    )
    print(f"[tjmg/single_page] rows: {len(df)}")

    # Zero hits (with a date filter, for the same reason).
    state["scenario"] = "no_results"
    counters.clear()
    df = scraper.cjsg(
        "juscraper_probe_zero_hits_xyzqwe",
        paginas=1,
        data_julgamento_inicio="01/01/2025",
        data_julgamento_fim="31/01/2025",
    )
    print(f"[tjmg/no_results] rows: {len(df)} (expected 0)")

    # The database error: only the download, which raises on it. The hook
    # does not save this page, so a "muitos resultados" answer does not
    # overwrite the sample.
    state["scenario"] = None
    try:
        scraper.cjsg_download("dano moral", paginas=1)
    except TJMGBuscaSemListaError as exc:
        (dest / "erro_ora.html").write_bytes(state["last_search"])
        print(f"[tjmg/erro_ora] {exc} -> erro_ora.html")
    except ValueError as exc:
        print(f"[tjmg/erro_ora] no ORA-20000 this time ({exc}); erro_ora.html kept")
    # A common search with too many hits: the download raises ValueError.
    state["scenario"] = "muitos_resultados"
    try:
        scraper.cjsg_download(
            "dano moral",
            paginas=1,
            data_julgamento_inicio="01/01/2025",
            data_julgamento_fim="31/03/2025",
        )
    except ValueError as exc:
        print(f"[tjmg/muitos_resultados] {exc}")
    else:
        raise SystemExit("[tjmg/muitos_resultados] the portal listed the hits; pick a broader search")
    # The categorized search, followed into each category's list.
    state["scenario"] = "categorizada"
    counters.clear()
    scraper.cjsg_download(
        "usucapiao",
        paginas=range(1, 3),
        data_julgamento_inicio="01/01/2025",
        data_julgamento_fim="31/12/2025",
    )


if __name__ == "__main__":
    main()
