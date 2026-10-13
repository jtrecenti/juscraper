"""Capture cjsg samples for TRF3 (busca de jurisprudência, ``web.trf3.jus.br``).

Run from repo root::

    python -m tests.fixtures.capture.trf3_cjsg

Writes to ``tests/trf3/samples/cjsg/``. Separate from ``trf3.py`` (cpopg),
because the jurisprudence portal is a different system from the PJe.

Every result page comes from ``TRF3Scraper.cjsg_download``, the public method
behind ``cjsg``, so drift between the scraper and the portal breaks this
script first. Each saved file is one page of the "lista resumida" as the
scraper decoded it, written back as UTF-8.

The opening tab is the exception: ``cjsg_download`` reads it only to open the
session and does not return its body. The script fetches it with a session of
its own, built by the scraper's :func:`build_cjsg_session` and sent to the
scraper's :data:`INDEX_URL` with the timeout of the scraper's HTTP profile.
That request has no retry: if it times out, run the script again.

Scenarios:

* ``index_acordaos.html``: the ``GET home/index/0`` that opens the session.
  The scraper ignores its body; the contracts reuse it for the opening GET.
* ``results_normal_page_01.html`` / ``_02.html``: acórdãos, "medicamento",
  julgados no 1º semestre de 2026 (several pages).
* ``single_page.html``: one process number, a handful of documents.
* ``no_results.html``: a term with zero hits.
* ``turmas_recursais_page_01.html``, ``monocraticas_page_01.html`` and
  ``monocraticas_turmas_recursais_page_01.html``: page 1 of each other base.
* ``acordaos_2012.html``: acórdãos julgados em 2012, older layout
  (``e-DJF3 Judicial 1 DATA:...``, órgão as ``TERCEIRA TURMA``).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import juscraper as jus
from juscraper.courts.trf3.cjsg_download import INDEX_URL, build_cjsg_session

from ._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

SEMESTRE = {"data_julgamento_inicio": "01/01/2026", "data_julgamento_fim": "30/06/2026"}


def _capture(scraper, dest: Path, filenames: dict[int, str], **busca) -> None:
    paginas = sorted(filenames)
    htmls = scraper.cjsg_download(paginas=paginas, **busca)
    for pagina, html in zip(paginas, htmls, strict=True):
        dump(dest / filenames[pagina], html.encode("utf-8"))
        logger.info("[trf3 cjsg] wrote %s", filenames[pagina])
    time.sleep(1.0)


def main() -> None:
    """Capture cjsg HTML samples for TRF3."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dest = samples_dir_for("trf3", "cjsg")
    scraper = jus.scraper("trf3", sleep_time=1.0)

    index = build_cjsg_session().get(
        INDEX_URL.format(indice=0), timeout=scraper.perfis_http["cjsg"].timeout,
    )
    index.raise_for_status()
    dump(dest / "index_acordaos.html", index.content)
    logger.info("[trf3 cjsg] wrote index_acordaos.html")

    _capture(
        scraper, dest,
        {1: "results_normal_page_01.html", 2: "results_normal_page_02.html"},
        pesquisa="medicamento", **SEMESTRE,
    )
    _capture(scraper, dest, {1: "single_page.html"}, numero_processo="5001743-27.2026.4.03.0000")
    _capture(scraper, dest, {1: "no_results.html"}, pesquisa="juscraper_probe_zero_hits_xyzqwe", **SEMESTRE)
    for base in ("turmas_recursais", "monocraticas", "monocraticas_turmas_recursais"):
        _capture(scraper, dest, {1: f"{base}_page_01.html"}, base=base, pesquisa="medicamento", **SEMESTRE)
    _capture(
        scraper, dest, {1: "acordaos_2012.html"},
        pesquisa="medicamento", data_julgamento_inicio="01/01/2012", data_julgamento_fim="31/12/2012",
    )


if __name__ == "__main__":
    main()
