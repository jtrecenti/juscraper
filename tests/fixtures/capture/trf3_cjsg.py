"""Capture cjsg samples for TRF3 (busca de jurisprudência, ``web.trf3.jus.br``).

Run from repo root::

    python -m tests.fixtures.capture.trf3_cjsg              # every scenario
    python -m tests.fixtures.capture.trf3_cjsg index_turmas_recursais

Writes to ``tests/trf3/samples/cjsg/``. Separate from ``trf3.py`` (cpopg),
because the jurisprudence portal is a different system from the PJe. Naming
scenarios on the command line captures only those, so a new sample can be
added without rewriting the others.

Every result page comes from ``TRF3Scraper.cjsg_download``, the public method
behind ``cjsg``, so drift between the scraper and the portal breaks this
script first. Each saved file is one page of the "lista resumida" as the
scraper decoded it, written back as UTF-8.

The opening tabs are the exception: ``cjsg_download`` reads them only to open
the session and to read the órgão dropdown, and does not return their body.
The script fetches them with a session of its own, built by the scraper's
:func:`build_cjsg_session` and sent to the scraper's :data:`INDEX_URL` with
the timeout of the scraper's HTTP profile. That request has no retry: if it
times out, run the scenario again.

Scenarios:

* ``index_acordaos``: the ``GET home/index/0`` that opens the session, with
  the órgão dropdown of the acórdãos base. The contracts reuse it for the
  opening GET.
* ``index_turmas_recursais``: the ``GET home/index/1``, with the órgão
  dropdown of the Turmas Recursais base.
* ``results_normal``: acórdãos, "medicamento", julgados no 1º semestre de
  2026, pages 1 and 2.
* ``single_page``: one process number, a handful of documents.
* ``no_results``: a term with zero hits.
* ``outras_bases``: page 1 of ``turmas_recursais``, ``monocraticas`` and
  ``monocraticas_turmas_recursais``.
* ``acordaos_2012``: acórdãos julgados em 2012, older layout
  (``e-DJF3 Judicial 1 DATA:...``, órgão as ``TERCEIRA TURMA``).
"""
from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from pathlib import Path

import juscraper as jus
from juscraper.courts.trf3.cjsg_download import BASES, INDEX_URL, PERFIL_CJSG, build_cjsg_session

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


def _capture_aba(scraper, dest: Path, base: str) -> None:
    nome = f"index_{base}.html"
    aba = build_cjsg_session().get(
        INDEX_URL.format(indice=BASES[base][0]), timeout=scraper.perfis_http[PERFIL_CJSG].timeout,
    )
    aba.raise_for_status()
    dump(dest / nome, aba.content)
    logger.info("[trf3 cjsg] wrote %s", nome)
    time.sleep(1.0)


def _outras_bases(scraper, dest: Path) -> None:
    for base in ("turmas_recursais", "monocraticas", "monocraticas_turmas_recursais"):
        _capture(scraper, dest, {1: f"{base}_page_01.html"}, base=base, pesquisa="medicamento", **SEMESTRE)


CENARIOS: dict[str, Callable[..., None]] = {
    "index_acordaos": lambda scraper, dest: _capture_aba(scraper, dest, "acordaos"),
    "index_turmas_recursais": lambda scraper, dest: _capture_aba(scraper, dest, "turmas_recursais"),
    "results_normal": lambda scraper, dest: _capture(
        scraper, dest,
        {1: "results_normal_page_01.html", 2: "results_normal_page_02.html"},
        pesquisa="medicamento", **SEMESTRE,
    ),
    "single_page": lambda scraper, dest: _capture(
        scraper, dest, {1: "single_page.html"}, numero_processo="5001743-27.2026.4.03.0000",
    ),
    "no_results": lambda scraper, dest: _capture(
        scraper, dest, {1: "no_results.html"}, pesquisa="juscraper_probe_zero_hits_xyzqwe", **SEMESTRE,
    ),
    "outras_bases": _outras_bases,
    "acordaos_2012": lambda scraper, dest: _capture(
        scraper, dest, {1: "acordaos_2012.html"},
        pesquisa="medicamento", data_julgamento_inicio="01/01/2012", data_julgamento_fim="31/12/2012",
    ),
}


def main(argv: list[str] | None = None) -> None:
    """Capture cjsg HTML samples for TRF3: the scenarios named in ``argv``, or all."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cenarios", nargs="*", help=f"default: every scenario ({', '.join(CENARIOS)})")
    cenarios = parser.parse_args(argv).cenarios or list(CENARIOS)
    desconhecidos = [c for c in cenarios if c not in CENARIOS]
    if desconhecidos:
        parser.error(f"unknown scenario(s): {', '.join(desconhecidos)}")

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dest = samples_dir_for("trf3", "cjsg")
    scraper = jus.scraper("trf3", sleep_time=1.0)
    for cenario in cenarios:
        CENARIOS[cenario](scraper, dest)


if __name__ == "__main__":
    main()
