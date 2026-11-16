"""Capture cjsg samples for TJSC.

Run from repo root::

    python -m tests.fixtures.capture.tjsc

Saves raw HTML responses (eproc) under ``tests/tjsc/samples/cjsg/``.
TJSC is dual-URL: page 1 hits ``listar_resultados``; page 2+ hit
``ajax_paginar_resultado``. The script exercises both.
"""
from typing import Any

import requests

from juscraper.courts.tjsc.download import build_cjsg_form_body, cjsg_url_for_page

from ._util import dump, samples_dir_for


def _capture(
    session: requests.Session, dest, pesquisa: str, pagina_1based: int, filename: str, **filtros: Any,
) -> None:
    body = build_cjsg_form_body(pesquisa, page=pagina_1based, **filtros)
    url = cjsg_url_for_page(pagina_1based)
    response = session.post(url, data=body, timeout=60, allow_redirects=False)
    response.raise_for_status()
    if 300 <= response.status_code < 400:
        raise RuntimeError(f"[tjsc] busca redirecionada para {response.headers.get('Location')!r}")
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
    # Classe com sigla de duas palavras (``HC TR - Habeas Corpus Criminal TR``), 16/11/2026.
    _capture(session, dest, "habeas corpus", 1, "classe_sigla_com_espaco.html")
    _capture(
        session, dest, "direito", 1, "filtro_data_julgamento.html",
        dt_decisao_inicio="10/03/2025", dt_decisao_fim="13/03/2025",
    )
    # Registro sem link de processo: o número vem só como texto (#495). O
    # único conhecido tem julgamento em 09/07/2027 na fonte; a busca por
    # processo=0000.14.36.787202-3 não o encontra (15/11/2026).
    _capture(
        session, dest, "", 1, "processo_sem_link.html",
        dt_decisao_inicio="09/07/2027", dt_decisao_fim="09/07/2027",
    )
    # Número com o sufixo ``/SC`` no link, em vez de ``/TJSC`` (16/11/2026):
    # a página traz números antigos com os dois sufixos.
    _capture(
        session, dest, "habeas corpus", 1, "processo_sufixo_sc.html",
        dt_decisao_inicio="01/01/2005", dt_decisao_fim="31/12/2006",
    )


if __name__ == "__main__":
    main()
