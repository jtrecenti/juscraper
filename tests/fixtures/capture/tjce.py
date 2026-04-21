"""Capture cjsg samples for TJCE.

TJCE requires TLS ``SECLEVEL=1`` (see
``src/juscraper/courts/tjce/cjsg_download.py::_TJCETLSAdapter``). This script
mounts the same adapter so captures succeed end-to-end.

Run from repo root::

    python -m tests.fixtures.capture.tjce
"""
from juscraper.courts.tjce.cjsg_download import _TJCETLSAdapter

from ._util import capture_cjsg_samples


def main() -> None:
    """Capture cjsg samples for TJCE (uses the SECLEVEL=1 TLS adapter)."""
    capture_cjsg_samples(
        tribunal="tjce",
        base_url="https://esaj.tjce.jus.br/",
        adapters={"https://": _TJCETLSAdapter()},
    )


if __name__ == "__main__":
    main()
