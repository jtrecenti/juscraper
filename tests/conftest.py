"""Global pytest fixtures for juscraper tests."""
from pathlib import Path

import pytest


@pytest.fixture
def samples_dir() -> Path:
    """Root of test fixtures."""
    return Path(__file__).parent
