"""Live integration test for TRF5 ``cpopg``.

Marked ``integration`` and skipped by default. Run with ``pytest -m integration``.
"""
from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus

# A consulta pública PJe do TRF5 é protegida por Akamai: de IPs de datacenter/CI
# o portal devolve 403 ``Access Denied`` e o scraper levanta
# ``BotChallengeBlockedError``. O marker ``anti_bot`` faz o conftest converter
# esse bloqueio em xfail (falha ambiental, não regressão). Ver issue #292.
pytestmark = pytest.mark.anti_bot

# CNJ pulled from data/amostra_jf_primeiro_grau.csv (CEJUSC Maceió, AL).
_KNOWN_GOOD_CNJ = "00584573120254058000"

# CNJ that — at the time of writing — has > 15 movs and therefore exercises
# the Richfaces slider paginator (fix for the bug where only the first 15
# movs were ever scraped).
_PAGINATED_CNJ = "08147767120224058100"


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
def test_cpopg_returns_all_movs_pages() -> None:
    """Process with > 15 movs must surface every page, not just the first 15."""
    scraper = jus.scraper("trf5", sleep_time=0.5)
    df = scraper.cpopg(_PAGINATED_CNJ)
    movs = df["movimentacoes"].iloc[0]
    assert isinstance(movs, list)
    assert len(movs) > 15, f"expected > 15 movs (paginated), got {len(movs)}"
    # Pagination is healthy when later pages bring *different* rows, not a
    # re-fetch of page 1. A stuck slider cursor would re-fetch page 1 on every
    # page, so the set of distinct (data, descricao) pairs would not exceed a
    # single page. Assert it does. Do NOT assert global uniqueness of
    # (data, descricao) — the PJe legitimately emits several events with the
    # same second-precision timestamp and description within a single page, so
    # that key is not unique in real data. ``page_size`` is the PJe movimentações
    # page size (~15; live capture: TRF1 55 movs/4 pages, TRF5 505/34).
    page_size = 15
    pairs = [(m["data"], m["descricao"]) for m in movs]
    assert len(set(pairs)) > page_size, "page 2 repeated page 1 (stuck pagination cursor)"
    # Regression guard: paginated movs (page >= 2) must carry clean accents.
    # The Richfaces fragment is UTF-8; decoding it as latin-1 turns "petição"
    # into "petiÃ§Ã£o". Without this, the count/pagination checks above pass
    # even when every paginated row is mojibaked.
    descricoes = " ".join(m["descricao"] for m in movs)
    assert "Ã§" not in descricoes and "Ã£" not in descricoes, (
        "mojibake nas movs paginadas — fragmento UTF-8 decodificado como latin-1"
    )


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
