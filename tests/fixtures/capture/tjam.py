"""Capture cjsg samples for TJAM.

Run from repo root::

    python -m tests.fixtures.capture.tjam
"""
from ._util import capture_cjsg_samples


def main() -> None:
    """Capture cjsg samples for TJAM."""
    capture_cjsg_samples(
        tribunal="tjam",
        base_url="https://consultasaj.tjam.jus.br/",
    )


if __name__ == "__main__":
    main()
