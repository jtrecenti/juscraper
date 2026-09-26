"""Live integration tests for TJMG ``cposg`` (hit ``www4.tjmg.jus.br``)."""
from __future__ import annotations

import pytest

import juscraper as jus


@pytest.mark.integration
def test_cposg_live_returns_advogados():
    df = jus.scraper("tjmg").cposg("5000344-57.2025.8.13.0461")

    assert len(df) >= 1
    partes = df.iloc[0]["partes"]
    assert partes
    assert any(p["advogados"] for p in partes)
