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
