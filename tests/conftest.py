"""Global pytest fixtures for juscraper tests."""
from pathlib import Path

import pytest


@pytest.fixture
def tests_dir() -> Path:
    """Path to ``tests/``. Compose with ``tribunal`` and ``samples`` to reach fixtures.

    Most tests should prefer ``tests._helpers.load_sample`` instead.
    """
    return Path(__file__).parent
