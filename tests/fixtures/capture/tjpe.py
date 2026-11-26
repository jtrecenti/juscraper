"""Capture cjsg samples for TJPE.

Run from repo root::

    python -m tests.fixtures.capture.tjpe              # todos os cenários
    python -m tests.fixtures.capture.tjpe monocraticas # só os cenários citados

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

Scenarios (the first three per the umbrella issue, #197):

- **escolha** — 4 chamadas (GET + POST consulta=escolha + POST escolha
  + AJAX page 2). Files: ``step_01_consulta.html``, ``step_02_escolha.html``,
  ``step_03_resultado.html``, ``step_04_pagina_02.xml``.
- **simples** — 3 chamadas (GET + POST consulta=results + AJAX page 2).
  Files (reusam ``step_01_consulta.html`` do escolha):
  ``simples_resultado.html``, ``simples_pagina_02.xml``.
- **no_results** — 2 chamadas (GET + POST consulta com 0 docs). File:
  ``no_results.html``.
- **monocraticas** — 3 chamadas (GET + POST consulta=results + AJAX
  page 2), com ``tipo_decisao="monocraticas"``. O bloco de cada decisão
  não traz ``Ementa``: traz ``Data da Publicação`` e ``Decisão``. Files:
  ``monocraticas_resultado.html``, ``monocraticas_pagina_02.xml``.

The capture installs a response hook on the scraper's ``Session`` and
classifies each response by URL path + HTTP method + scenario. Samples are
byte-identical to what the live backend served.
"""
from __future__ import annotations

import sys
from urllib.parse import urlparse

import requests

import juscraper as jus

from ._util import samples_dir_for

# Cenário -> (pesquisa, kwargs do ``cjsg``), na ordem em que rodam.
CENARIOS: dict[str, tuple[str, dict]] = {
    # escolha: tipo_decisao="todos" forces the chooser page (4 calls).
    "escolha": ("dano moral", {"paginas": range(1, 3), "tipo_decisao": "todos"}),
    # simples: default tipo_decisao="acordaos" skips the chooser (3 calls).
    "simples": ("dano moral", {"paginas": range(1, 3)}),
    # no_results: improbable term yields 0 documents (2 calls; AJAX skipped).
    "no_results": ("juscraperprobeztzeroxyz", {"paginas": 1}),
    # monocraticas: só a caixa das monocráticas, sem escolha (3 calls).
    "monocraticas": ("dano moral", {"paginas": range(1, 3), "tipo_decisao": "monocraticas"}),
}


def _proxima_pagina_ajax(counters: dict[str, int]) -> int:
    """Número da página da próxima resposta AJAX (a 1ª é a 2ª página)."""
    counters["ajax"] = counters.get("ajax", 0) + 1
    return counters["ajax"] + 1


def _classify_escolha(method: str, path: str, counters: dict[str, int]) -> str | None:
    if method == "GET" and path == "consulta.xhtml":
        return "step_01_consulta.html"
    if method != "POST":
        return None
    if path == "consulta.xhtml":
        return "step_02_escolha.html"
    if path == "escolhaResultado.xhtml":
        return "step_03_resultado.html"
    if path == "resultado.xhtml":
        page_num = _proxima_pagina_ajax(counters)
        # GET=01, POST=02, escolha=03, AJAX=04+
        return f"step_{page_num + 2:02d}_pagina_{page_num:02d}.xml"
    return None


def _classify(
    method: str,
    url: str,
    scenario: str,
    counters: dict[str, int],
) -> str | None:
    """Pick the filename for a given response, or ``None`` to skip."""
    path = urlparse(url).path.rsplit("/", 1)[-1]

    if scenario == "escolha":
        return _classify_escolha(method, path, counters)
    # Nos demais cenários, o GET de consulta.xhtml reusa o
    # step_01_consulta.html do escolha; não é regravado.
    if method != "POST":
        return None
    if path == "consulta.xhtml":
        return "no_results.html" if scenario == "no_results" else f"{scenario}_resultado.html"
    if path == "resultado.xhtml" and scenario != "no_results":
        return f"{scenario}_pagina_{_proxima_pagina_ajax(counters):02d}.xml"
    return None


def main() -> None:
    """Capture cjsg HTML/XML samples for TJPE.

    Sem argumentos, roda todos os cenários; com argumentos, só os citados.
    """
    pedidos = set(sys.argv[1:])
    if desconhecidos := pedidos - set(CENARIOS):
        raise SystemExit(f"Cenário desconhecido: {sorted(desconhecidos)}")
    dest = samples_dir_for("tjpe", "cjsg")
    scraper = jus.scraper("tjpe")

    state: dict[str, str | None] = {"scenario": None}
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
        scraper.session.hooks["response"].append(hook)

    scraper.session.hooks["response"].append(hook)
    primeiro = True
    for scenario, (pesquisa, kwargs) in CENARIOS.items():
        if pedidos and scenario not in pedidos:
            continue
        if not primeiro:
            _reset_session()
        primeiro = False
        state["scenario"] = scenario
        counters.clear()
        df = scraper.cjsg(pesquisa, **kwargs)
        print(f"[tjpe/{scenario}] DataFrame columns: {list(df.columns)}")
        print(f"[tjpe/{scenario}] rows: {len(df)}")


if __name__ == "__main__":
    main()
