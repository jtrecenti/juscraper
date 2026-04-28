"""Capture cjsg samples for TJAC.

Run from repo root::

    python -m tests.fixtures.capture.tjac
"""
from ._util import capture_cjsg_samples


def main() -> None:
    """Capture cjsg samples for TJAC."""
    capture_cjsg_samples(
        tribunal="tjac",
        base_url="https://esaj.tjac.jus.br/",
    )


if __name__ == "__main__":
    main()
