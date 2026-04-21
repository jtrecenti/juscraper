"""Capture samples for TJSP across all public endpoints.

TJSP exposes four public methods (``cjsg``, ``cjpg``, ``cpopg``, ``cposg``)
plus ``method='html'``/``method='api'`` variants for the last two. This
script exercises each flow against the live eSAJ and API hosts and dumps
raw responses under ``tests/tjsp/samples/<endpoint>/``.

Run from repo root::

    python -m tests.fixtures.capture.tjsp

Override the CNJ of test via ``--cnj`` if the default is retired::

    python -m tests.fixtures.capture.tjsp --cnj 1000149-71.2024.8.26.0346

The script is intentionally linear — each endpoint is a separate function,
and ``main()`` calls them in order. If one flow breaks (e.g., API returns
503), the others still produce samples.
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import requests

from ._util import (
    TJSP_CHROME_HEADERS,
    build_session,
    capture_cjsg_samples,
    dump,
    make_tjsp_cjpg_params,
    make_tjsp_cjsg_body,
    samples_dir_for,
)

ESAJ_BASE = "https://esaj.tjsp.jus.br/"
API_BASE = "https://api.tjsp.jus.br/"

# CNJ used by the existing integration tests (tests/tjsp/test_cpopg.py).
# If it disappears from the TJSP index, pass --cnj to override.
DEFAULT_CNJ = "1000149-71.2024.8.26.0346"


def _clean_cnj(cnj: str) -> str:
    """Strip non-digit characters from a CNJ. Mirrors ``utils.cnj.clean_cnj``."""
    return re.sub(r"[^0-9]", "", cnj)


# ---------- cjsg ---------------------------------------------------------

def capture_cjsg() -> None:
    """Capture cjsg samples via the shared helper with the TJSP body/headers."""
    capture_cjsg_samples(
        tribunal="tjsp",
        base_url=ESAJ_BASE,
        headers=TJSP_CHROME_HEADERS,
        body_builder=make_tjsp_cjsg_body,
    )


# ---------- cjpg ---------------------------------------------------------

def _fetch_cjpg_page1(session: requests.Session, pesquisa: str) -> requests.Response:
    # Warm the session on the cjpg home page so the server sets the JSESSIONID
    # and any CSRF cookies; then submit the query. The scraper itself doesn't
    # do this, but live browsers do — the eSAJ cjpg backend increasingly
    # refuses anonymous queries without a prior cookie-setting hit.
    session.get(f"{ESAJ_BASE}cjpg/open.do", timeout=60)
    params = make_tjsp_cjpg_params(pesquisa)
    r = session.get(f"{ESAJ_BASE}cjpg/pesquisar.do", params=params, timeout=60)
    r.raise_for_status()
    return r


def _fetch_cjpg_page_n(session: requests.Session, page: int) -> requests.Response:
    url = f"{ESAJ_BASE}cjpg/trocarDePagina.do"
    params: dict[str, str] = {"pagina": str(page), "conversationId": ""}
    r = session.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r


def capture_cjpg() -> None:
    """Capture cjpg samples (typical multi-page, single-page, no-results).

    Each scenario runs in its own try/except so a flaky 500 on one request
    (common on the TJSP cjpg paginator) does not abort the rest. Uses a
    fresh session per scenario — shared cookies across unrelated queries
    make the server drop state more often than not.
    """
    dest = samples_dir_for("tjsp", "cjpg")

    # Typical multi-page — tried once with a fresh session and a sleep
    # between page 1 and page 2, because the paginator is stateful.
    try:
        session = build_session(headers=TJSP_CHROME_HEADERS)
        r1 = _fetch_cjpg_page1(session, "dano moral")
        dump(dest / "results_normal_page_01.html", r1.content)
        time.sleep(1.5)
        r2 = _fetch_cjpg_page_n(session, 2)
        dump(dest / "results_normal_page_02.html", r2.content)
        print("[tjsp] cjpg typical ('dano moral') → 2 pages saved")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[tjsp] cjpg typical FAILED: {exc}")

    try:
        session = build_session(headers=TJSP_CHROME_HEADERS)
        r_single = _fetch_cjpg_page1(
            session, "usucapiao extraordinario predio rural familia juizado"
        )
        dump(dest / "single_page.html", r_single.content)
        print("[tjsp] cjpg single_page → saved")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[tjsp] cjpg single_page FAILED: {exc}")

    try:
        session = build_session(headers=TJSP_CHROME_HEADERS)
        r_none = _fetch_cjpg_page1(session, "juscraper_probe_zero_hits_xyzqwe")
        dump(dest / "no_results.html", r_none.content)
        print("[tjsp] cjpg no_results → saved")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[tjsp] cjpg no_results FAILED: {exc}")


# ---------- cpopg html ---------------------------------------------------

def capture_cpopg_html(cnj: str) -> None:
    """Capture cpopg samples for ``method='html'``.

    Fetches ``search.do`` for ``cnj`` and one ``show.do`` per link returned.
    Overwrites ``show_standard.html`` — legacy synthetic samples live in the
    same directory under their kept names (``show_standard.html``,
    ``show_alternative.html``) and remain for unit tests.
    """
    dest = samples_dir_for("tjsp", "cpopg")
    session = build_session(headers=TJSP_CHROME_HEADERS)

    # search
    id_clean = _clean_cnj(cnj)
    num, dv = cnj.split("-")[0], cnj.split("-")[1][:2]
    ano = cnj.split(".")[1]
    orgao = cnj.split(".")[-1]
    params = {
        "conversationId": "",
        "cbPesquisa": "NUMPROC",
        "numeroDigitoAnoUnificado": f"{num}-{dv}.{ano}",
        "foroNumeroUnificado": orgao,
        "dadosConsulta.valorConsultaNuUnificado": cnj,
        "dadosConsulta.valorConsulta": "",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
    }
    r_search = session.get(f"{ESAJ_BASE}cpopg/search.do", params=params, timeout=60)
    r_search.raise_for_status()
    dump(dest / "search.html", r_search.content)
    print(f"[tjsp] cpopg html search for {cnj} → saved")

    # parse the search response to discover the processo.codigo param
    # (simplified: regex over the HTML; scraper uses BeautifulSoup but we
    # just need the codes for sample capture)
    codigos = re.findall(r"processo\.codigo=([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        print(f"[tjsp] cpopg html: no processo.codigo in search response for {cnj}")
        return
    # fetch show.do for first code only — extra codes add noise
    cd = codigos[0]
    r_show = session.get(
        f"{ESAJ_BASE}cpopg/show.do",
        params={"processo.codigo": cd},
        timeout=60,
    )
    r_show.raise_for_status()
    dump(dest / "show_real.html", r_show.content)
    print(f"[tjsp] cpopg html show for codigo={cd} → saved")
    _ = id_clean  # referenced for symmetry with scraper internals


# ---------- cpopg api ----------------------------------------------------

def capture_cpopg_api(cnj: str) -> None:
    """Capture cpopg samples for ``method='api'``.

    GET search/numproc → POST dadosbasicos → 4× GET components (partes,
    movimentacao, incidente, audiencia). Each JSON is dumped under
    ``tests/tjsp/samples/cpopg/api_*.json``.
    """
    dest = samples_dir_for("tjsp", "cpopg")
    session = build_session(headers=TJSP_CHROME_HEADERS)
    id_clean = _clean_cnj(cnj)

    r_search = session.get(
        f"{API_BASE}processo/cpopg/search/numproc/{id_clean}", timeout=60
    )
    r_search.raise_for_status()
    dump(dest / "api_search.json", r_search.content)
    print(f"[tjsp] cpopg api search/numproc/{id_clean} → saved")

    processos = r_search.json()
    if not processos:
        print("[tjsp] cpopg api: empty search response; skipping subsequent calls")
        return

    cd = processos[0]["cdProcesso"]
    r_basicos = session.post(
        f"{API_BASE}processo/cpopg/dadosbasicos/{cd}",
        json={"cdProcesso": cd},
        timeout=60,
    )
    r_basicos.raise_for_status()
    dump(dest / "api_dadosbasicos.json", r_basicos.content)
    print(f"[tjsp] cpopg api dadosbasicos/{cd} → saved")

    for comp in ("partes", "movimentacao", "incidente", "audiencia"):
        r_comp = session.get(f"{API_BASE}processo/cpopg/{comp}/{cd}", timeout=60)
        r_comp.raise_for_status()
        dump(dest / f"api_{comp}.json", r_comp.content)
        print(f"[tjsp] cpopg api {comp}/{cd} → saved")


# ---------- cposg html ---------------------------------------------------

def capture_cposg_html(cnj: str) -> None:
    """Capture cposg samples for ``method='html'``.

    Flow: GET ``open.do?gateway=true`` (warm up cookies) → GET ``search.do``
    → GET ``show.do`` per link. Only the common ``listagemDeProcessos``
    variant is captured automatically; modal (``modalIncidentes``) and
    simple variants require specific CNJs — capture those manually and
    save as ``search_modal.html`` / ``search_simple.html`` if needed.
    """
    dest = samples_dir_for("tjsp", "cposg")
    session = build_session(headers=TJSP_CHROME_HEADERS)

    r_open = session.get(f"{ESAJ_BASE}cposg/open.do", params={"gateway": "true"}, timeout=60)
    r_open.raise_for_status()
    dump(dest / "open.html", r_open.content)
    print("[tjsp] cposg html open → saved")

    num, dv = cnj.split("-")[0], cnj.split("-")[1][:2]
    ano = cnj.split(".")[1]
    orgao = cnj.split(".")[-1]
    params = {
        "conversationId": "",
        "paginaConsulta": "1",
        "localPesquisa.cdLocal": "-1",
        "cbPesquisa": "NUMPROC",
        "tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": f"{num}-{dv}.{ano}",
        "foroNumeroUnificado": orgao,
        "dePesquisaNuUnificado": cnj,
        "dePesquisa": "",
        "uuidCaptcha": "",
        "pbEnviar": "Pesquisar",
    }
    r_search = session.get(f"{ESAJ_BASE}cposg/search.do", params=params, timeout=60)
    r_search.raise_for_status()
    dump(dest / "search_listagem.html", r_search.content)
    print(f"[tjsp] cposg html search for {cnj} → saved")

    codigos = re.findall(r"processo\.codigo=([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        # Try alternative selector for the "simple" response variant
        codigos = re.findall(r"cdProcesso[\"']\s+value=[\"']([A-Za-z0-9]+)", r_search.text)
    if not codigos:
        print(f"[tjsp] cposg html: no process code found in search response for {cnj}")
        return

    cd = codigos[0]
    r_show = session.get(
        f"{ESAJ_BASE}cposg/show.do",
        params={"processo.codigo": cd},
        timeout=60,
    )
    r_show.raise_for_status()
    dump(dest / "show.html", r_show.content)
    print(f"[tjsp] cposg html show for codigo={cd} → saved")


# ---------- cposg api ----------------------------------------------------

def capture_cposg_api(cnj: str) -> None:
    """Capture cposg samples for ``method='api'`` (single GET)."""
    dest = samples_dir_for("tjsp", "cposg")
    session = build_session(headers=TJSP_CHROME_HEADERS)
    id_clean = _clean_cnj(cnj)

    r = session.get(f"{API_BASE}processo/cposg/search/numproc/{id_clean}", timeout=60)
    r.raise_for_status()
    dump(dest / "api_search.json", r.content)
    print(f"[tjsp] cposg api search/numproc/{id_clean} → saved")


# ---------- orchestrator -------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cnj", default=DEFAULT_CNJ, help="CNJ for cpopg/cposg captures")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        choices=["cjsg", "cjpg", "cpopg_html", "cpopg_api", "cposg_html", "cposg_api"],
        help="Flows to skip",
    )
    args = parser.parse_args()

    flows = [
        ("cjsg", lambda: capture_cjsg()),
        ("cjpg", lambda: capture_cjpg()),
        ("cpopg_html", lambda: capture_cpopg_html(args.cnj)),
        ("cpopg_api", lambda: capture_cpopg_api(args.cnj)),
        ("cposg_html", lambda: capture_cposg_html(args.cnj)),
        ("cposg_api", lambda: capture_cposg_api(args.cnj)),
    ]
    for name, fn in flows:
        if name in args.skip:
            print(f"[tjsp] skipping {name}")
            continue
        try:
            fn()
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[tjsp] {name} FAILED: {exc}")

    root: Path = samples_dir_for("tjsp", "cjsg").parent
    print(f"[tjsp] done. See {root}")


if __name__ == "__main__":
    main()
