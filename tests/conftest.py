"""Shared pytest fixtures for juscraper tests.

Test-level helpers live in ``tests/helpers.py`` so they can be imported by
per-tribunal test files (pytest does not import ``conftest.py`` as a regular
module). Fixtures are kept here so pytest picks them up automatically.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from helpers import (
    DATA_ALVO_BR,
    DATA_ALVO_FIM_BR,
    DATA_ALVO_FIM_ISO,
    DATA_ALVO_ISO,
)


@pytest.fixture
def tests_dir() -> Path:
    """Path to ``tests/``. Compose with ``tribunal`` and ``samples`` to reach fixtures.

    Most tests should prefer ``tests._helpers.load_sample`` instead.
    """
    return Path(__file__).parent


@pytest.fixture
def data_alvo_br() -> str:
    """Start of the reference work week in Brazilian format (DD/MM/YYYY)."""
    return DATA_ALVO_BR


@pytest.fixture
def data_alvo_fim_br() -> str:
    """End of the reference work week in Brazilian format (DD/MM/YYYY)."""
    return DATA_ALVO_FIM_BR


@pytest.fixture
def data_alvo_iso() -> str:
    """Start of the reference work week in ISO format (YYYY-MM-DD)."""
    return DATA_ALVO_ISO


@pytest.fixture
def data_alvo_fim_iso() -> str:
    """End of the reference work week in ISO format (YYYY-MM-DD)."""
    return DATA_ALVO_FIM_ISO
