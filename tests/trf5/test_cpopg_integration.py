"""Live integration test for TRF5 ``cpopg``.

Marked ``integration`` and skipped by default. Run with ``pytest -m integration``.
"""
from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus

# CNJ pulled from data/amostra_jf_primeiro_grau.csv (CEJUSC Maceió, AL).
_KNOWN_GOOD_CNJ = "00584573120254058000"


@pytest.mark.integration
def test_cpopg_lookup_returns_real_data() -> None:
    """End-to-end: real HTTP call returns a populated DataFrame row."""
    scraper = jus.scraper("trf5", sleep_time=1.0)
    df = scraper.cpopg(_KNOWN_GOOD_CNJ)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == _KNOWN_GOOD_CNJ
    assert row["processo"] == "0058457-31.2025.4.05.8000"
    assert row["classe"]  # truthy
    assert isinstance(row["movimentacoes"], list) and row["movimentacoes"]


@pytest.mark.integration
def test_cpopg_missing_process_yields_id_only_row() -> None:
    """A CNJ the public portal does not surface yields a row with only ``id_cnj``."""
    # Synthetic CNJ shaped like a TRF5 process; the PJe form validates the
    # mask but the search returns no hits.
    missing_cnj = "00000000020994050000"
    scraper = jus.scraper("trf5", sleep_time=1.0)
    df = scraper.cpopg(missing_cnj)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == missing_cnj
    assert pd.isna(row.get("processo")) or row.get("processo") is None
