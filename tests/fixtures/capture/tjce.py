"""Capture cjsg samples for TJCE.

TJCE requires TLS ``SECLEVEL=1`` (see
``src/juscraper/courts/tjce/cjsg_download.py::_TJCETLSAdapter``). This script
mounts the same adapter so captures succeed end-to-end.

Run from repo root::

    python -m tests.fixtures.capture.tjce
"""
import logging

import juscraper as jus
from juscraper.courts.tjce.cjsg_download import _TJCETLSAdapter

from ._util import capture_cjsg_samples, dump, samples_dir_for


def main() -> None:
    """Capture cjsg samples for TJCE (uses the SECLEVEL=1 TLS adapter)."""
    capture_cjsg_samples(
        tribunal="tjce",
        base_url="https://esaj.tjce.jus.br/",
        adapters={"https://": _TJCETLSAdapter()},
        monocratica_query="usucapiao predio rural",
    )
    capture_acordao_samples()


def capture_acordao_samples() -> None:
    """Capture the page ``cjsg/getArquivo.do`` serves for an unknown ``cdAcordao``.

    The PDF of a real ``cdAcordao`` is not saved: the tests only need a body
    starting with ``%PDF``.
    """
    scraper = jus.scraper("tjce")
    resposta = scraper.session.get(
        f"{scraper.BASE_URL}cjsg/getArquivo.do", params={"cdAcordao": "999999999", "cdForo": "0"}, timeout=60
    )
    dump(samples_dir_for("tjce", "acordao") / "arquivo_nao_localizado.html", resposta.content)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
