"""Capture cjsg samples for TJAM.

Run from repo root::

    python -m tests.fixtures.capture.tjam
"""
from ._util import capture_cjsg_monocratica_sample, capture_cjsg_samples


def main() -> None:
    """Capture cjsg samples for TJAM."""
    capture_cjsg_samples(
        tribunal="tjam",
        base_url="https://consultasaj.tjam.jus.br/",
    )
    capture_cjsg_monocratica_sample("tjam", "https://consultasaj.tjam.jus.br/", "usucapiao predio rural")


if __name__ == "__main__":
    main()
