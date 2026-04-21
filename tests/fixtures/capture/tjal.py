"""Capture cjsg samples for TJAL.

Run from repo root::

    python -m tests.fixtures.capture.tjal
"""
from ._util import capture_cjsg_samples


def main() -> None:
    """Capture cjsg samples for TJAL."""
    capture_cjsg_samples(
        tribunal="tjal",
        base_url="https://www2.tjal.jus.br/",
    )


if __name__ == "__main__":
    main()
