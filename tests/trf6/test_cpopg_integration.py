"""Live integration test for TRF6 ``cpopg``.

Marked ``integration`` and skipped by default. Run with ``pytest -m integration``.
Requires the optional :mod:`txtcaptcha` package (and downloads a HuggingFace
CRNN on first call).
"""
from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus

# CNJ pulled from data/amostra_jf_primeiro_grau.csv — JEF process at the
# 3ª Vara Cível e JEF de Juiz de Fora, MG.
_KNOWN_GOOD_CNJ = "10052295520234063801"


@pytest.mark.integration
def test_cpopg_lookup_returns_real_data() -> None:
    """End-to-end: real HTTP + captcha solving → populated DataFrame row."""
    scraper = jus.scraper("trf6", sleep_time=1.0, max_captcha_attempts=5)
    df = scraper.cpopg(_KNOWN_GOOD_CNJ)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == _KNOWN_GOOD_CNJ
    assert row["processo"] == "1005229-55.2023.4.06.3801"
    assert row["classe"]  # truthy
    assert isinstance(row["movimentacoes"], list) and row["movimentacoes"]


@pytest.mark.integration
def test_cpopg_missing_process_yields_id_only_row() -> None:
    """A CNJ the public portal does not surface yields a row with only ``id_cnj``."""
    missing_cnj = "00000000020994060000"
    scraper = jus.scraper("trf6", sleep_time=1.0, max_captcha_attempts=5)
    df = scraper.cpopg(missing_cnj)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == missing_cnj
    assert pd.isna(row.get("processo")) or row.get("processo") is None
