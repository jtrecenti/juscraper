"""Release-tier integration tests: date-window filter across every tribunal.

Strategy
--------
For every supported tribunal we run the same three assertions against the
reference work-week window (10/03/2025 – 14/03/2025, Monday–Friday outside
holidays and the judicial recess of December/January/July):

1. ``cjsg`` with the date window fixed returns a non-empty DataFrame.
   Pesquisa is empty (``""``) by default; if the tribunal rejects that, we
   fall back to ``"direito"``.
2. If the DataFrame exposes a date-like column, every row falls inside the
   window. Tribunals without a date column only get the count check.
3. Pagination with ``paginas=range(1, 3)`` returns at least as many rows
   as ``paginas=1`` (strictly more if at least two pages exist).

These tests are expensive (one network round-trip per tribunal, sometimes
several). They are marked ``release`` so CI pipelines can skip them with
``-m "integration and not release"`` and only run the full suite before a
major release.

Usage
-----
All release tests       : ``pytest -m "integration and release"``
Fast CI integration only: ``pytest -m "integration and not release"``
Single tribunal         : ``pytest -m release -k tjrs``

Known failures
--------------
``KNOWN_FILTRO_FAILURES`` lists tribunals whose date-filter test is
currently broken; ``KNOWN_PAGINACAO_FAILURES`` does the same for the
pagination test (typically HTTP errors rather than filter bugs). Entries
use ``strict=True`` xfail, so a tribunal that starts passing becomes a
loud signal to remove it from the list.
"""
from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus
from helpers import (
    run_filtro_data_unica,
    run_paginacao_data_unica,
)

# Every tribunal registered in the public factory.
TRIBUNAIS = [
    "tjac", "tjal", "tjam", "tjap", "tjba", "tjce", "tjdft", "tjes",
    "tjgo", "tjmg", "tjms", "tjmt", "tjpa", "tjpb", "tjpe", "tjpi",
    "tjpr", "tjrj", "tjrn", "tjro", "tjrr", "tjrs", "tjsc", "tjsp",
    "tjto",
]

# Tribunals where the date filter itself is broken. Remove once fixed.
KNOWN_FILTRO_FAILURES = {
    "tjam": "cjsg returns no results for reasonable work weeks (filter/payload issue)",
    "tjap": "backend ignores date filter (returns current-date results)",
    "tjmt": "backend ignores filtro.periodoDataDe/Ate (returns current-date results)",
    "tjpa": "backend returns HTTP 400 on our payload",
    "tjpb": "backend ignores dt_inicio/dt_fim (returns 2025-05+ results)",
    "tjpi": "backend ignores date filter (returns 2025-09 results)",
    "tjrj": "legacy ASP.NET endpoint returns HTTP 500; scraper does not wire date filter",
    "tjrn": "date column comes through as NaT (parse issue or filter ignored)",
    "tjro": "backend returns HTTP 500 on our payload",
    "tjrr": "backend returns HTTP 502 (transient or payload issue)",
    "tjrs": "Solr payload returns zero results for the reference week",
}

# Tribunals where pagination specifically is broken (usually HTTP errors
# bubbling up on page 2). Subset of above for clarity.
KNOWN_PAGINACAO_FAILURES = {
    "tjpa": "backend returns HTTP 400 on our payload",
    "tjrj": "legacy endpoint returns HTTP 500",
    "tjro": "backend returns HTTP 500 on our payload",
}


def _xfail_if_known(tribunal: str, known: dict[str, str]):
    """Wrap *tribunal* with a strict xfail marker if it appears in *known*."""
    if tribunal in known:
        return pytest.param(
            tribunal,
            marks=pytest.mark.xfail(reason=known[tribunal], strict=True),
        )
    return tribunal


def _params(known: dict[str, str]):
    return [_xfail_if_known(t, known) for t in TRIBUNAIS]


@pytest.mark.integration
@pytest.mark.release
class TestReleaseFiltroDataUnica:
    """Date-window filter must work on every tribunal."""

    @pytest.mark.parametrize("tribunal", _params(KNOWN_FILTRO_FAILURES))
    def test_filtro_data_unica(self, tribunal):
        """cjsg com janela de datas retorna apenas resultados dentro do intervalo."""
        scraper = jus.scraper(tribunal)
        run_filtro_data_unica(scraper)

    @pytest.mark.parametrize("tribunal", _params(KNOWN_PAGINACAO_FAILURES))
    def test_paginacao_com_data_unica(self, tribunal):
        """Paginação respeita o filtro de data."""
        scraper = jus.scraper(tribunal)
        df1, df2 = run_paginacao_data_unica(scraper)
        assert isinstance(df1, pd.DataFrame)
        assert isinstance(df2, pd.DataFrame)
        # paginas=range(1,3) should never return fewer rows than paginas=1.
        # Strict ">" would flake for tribunals with a single page on the
        # target date, so we use ">=" and leave the multi-page case to the
        # non-date-filtered pagination tests already in per-tribunal files.
        assert len(df2) >= len(df1)
