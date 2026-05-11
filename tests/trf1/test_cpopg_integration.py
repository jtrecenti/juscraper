"""Live integration test for TRF1 ``cpopg``.

Marked ``integration`` and skipped by default. Run with ``pytest -m integration``.
"""
from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus

# CNJs picked from the user-supplied test set. ``KNOWN_GOOD`` has < 15 movs so
# it exercises the no-pagination short-circuit; ``PAGINATED`` has > 15 movs and
# locks in the Richfaces slider fix.
_KNOWN_GOOD_CNJ = "10088283520214013502"
_PAGINATED_CNJ = "10030632720234013304"


@pytest.mark.integration
def test_cpopg_lookup_returns_real_data() -> None:
    """End-to-end: real HTTP call returns a populated DataFrame row."""
    scraper = jus.scraper("trf1", sleep_time=1.0)
    df = scraper.cpopg(_KNOWN_GOOD_CNJ)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == _KNOWN_GOOD_CNJ
    assert row["processo"] == "1008828-35.2021.4.01.3502"
    assert row["classe"]
    assert isinstance(row["movimentacoes"], list) and row["movimentacoes"]


@pytest.mark.integration
def test_cpopg_returns_all_movs_pages() -> None:
    """Process with > 15 movs must surface every page, not just the first 15."""
    scraper = jus.scraper("trf1", sleep_time=0.5)
    df = scraper.cpopg(_PAGINATED_CNJ)
    movs = df["movimentacoes"].iloc[0]
    assert isinstance(movs, list)
    assert len(movs) > 15, f"expected > 15 movs (paginated), got {len(movs)}"
    pairs = [(m["data"], m["descricao"]) for m in movs]
    assert len(pairs) == len(set(pairs)), "duplicate movs after pagination"


@pytest.mark.integration
def test_cpopg_missing_process_yields_id_only_row() -> None:
    """A CNJ the public portal cannot surface yields a row with only ``id_cnj``."""
    missing_cnj = "00000000019994010000"
    scraper = jus.scraper("trf1", sleep_time=1.0)
    df = scraper.cpopg(missing_cnj)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == missing_cnj
    assert pd.isna(row.get("processo")) or row.get("processo") is None
