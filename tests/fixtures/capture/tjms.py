"""Capture cjsg samples for TJMS.

Run from repo root::

    python -m tests.fixtures.capture.tjms
"""
from ._util import capture_cjsg_samples


def main() -> None:
    """Capture cjsg samples for TJMS."""
    capture_cjsg_samples(
        tribunal="tjms",
        base_url="https://esaj.tjms.jus.br/",
    )


if __name__ == "__main__":
    main()
