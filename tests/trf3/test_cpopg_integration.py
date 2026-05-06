"""Live integration test for TRF3 ``cpopg``.

Marked ``integration`` and skipped by default (``pytest`` excludes the marker
unless ``-m integration`` is passed). Hits the live PJe deployment and
exercises the same code path the contract tests mock.
"""
from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus

# CNJ pulled from data/amostra_jf_primeiro_grau.csv. Picked because it's a
# recent JEF process from São José do Rio Preto (TRF3 / SP) that has many
# movements but is not under sigilo.
_KNOWN_GOOD_CNJ = "50059460920254036324"

# CNJ that — at the time of writing — has > 15 movs and therefore exercises
# the Richfaces slider paginator. We assert the count exceeds 15 to lock in
# the fix for the original bug (only the first page was being scraped).
_PAGINATED_CNJ = "50018470420224036323"


@pytest.mark.integration
def test_cpopg_lookup_returns_real_data() -> None:
    """End-to-end: real HTTP call returns a populated DataFrame row."""
    scraper = jus.scraper("trf3", sleep_time=1.0)
    df = scraper.cpopg(_KNOWN_GOOD_CNJ)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == _KNOWN_GOOD_CNJ
    assert row["processo"] == "5005946-09.2025.4.03.6324"
    assert row["classe"]  # truthy
    assert isinstance(row["movimentacoes"], list) and row["movimentacoes"]


@pytest.mark.integration
def test_cpopg_returns_all_movs_pages() -> None:
    """Process with > 15 movs must surface every page, not just the first 15."""
    scraper = jus.scraper("trf3", sleep_time=0.5)
    df = scraper.cpopg(_PAGINATED_CNJ)
    movs = df["movimentacoes"].iloc[0]
    assert isinstance(movs, list)
    assert len(movs) > 15, f"expected > 15 movs (paginated), got {len(movs)}"
    # Sanity: no duplicate (data, descricao) pairs — duplicates would mean
    # we're posting the same page twice instead of advancing.
    pairs = [(m["data"], m["descricao"]) for m in movs]
    assert len(pairs) == len(set(pairs)), "duplicate movs after pagination"
