"""Regression tests for the TJPB cjsg local post-filter on ``data_julgamento``.

The TJPB backend filters ``dt_inicio``/``dt_fim`` on an internal disponibilização
date, not on ``dt_ementa``. The client therefore re-applies the user's window
locally on the parsed ``data_julgamento`` column. Refs #195: that filter must
work even when only one of the two dates is supplied, and must accept any of
the canonical input formats (BR, ISO, ``date``).
"""
from datetime import date

import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.courts.tjpb.download import BASE_URL, SEARCH_URL, TOKEN_RE
from tests._helpers import load_sample, load_sample_bytes

_HOME_HTML_BYTES = load_sample_bytes("tjpb", "cjsg/home.html")
_TOKEN_MATCH = TOKEN_RE.search(_HOME_HTML_BYTES.decode("utf-8"))
assert _TOKEN_MATCH is not None, "captured TJPB home.html lacks <meta name='_token' ...>"

# Sample has 10 hits with dt_ementa spanning 2022-2025:
#   2022 → 1 row (20/10/2022)
#   2023 → 3 rows (13/02, 21/11, 15/12)
#   2024 → 2 rows (29/04, 23/08)
#   2025 → 4 rows (14/01, 12/04 ×2, 27/05)
_RESULTS_BODY = load_sample("tjpb", "cjsg/results_normal_page_01.json")


def _stub_endpoints() -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=_HOME_HTML_BYTES,
        status=200,
        content_type="text/html; charset=UTF-8",
    )
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=_RESULTS_BODY,
        status=200,
        content_type="application/json",
    )


@responses.activate
def test_postfilter_only_inicio(mocker):
    """Refs #195: post-filter must run when only ``data_julgamento_inicio`` is set."""
    mocker.patch("time.sleep")
    _stub_endpoints()

    df = jus.scraper("tjpb").cjsg(
        "dano moral", paginas=1, data_julgamento_inicio="01/01/2024"
    )

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 6  # 2 from 2024 + 4 from 2025
    assert df["data_julgamento"].min() >= date(2024, 1, 1)
    # Pre-2024 process must be filtered out:
    assert "0122740-60.2012.8.15.2001" not in df["processo"].values


@responses.activate
def test_postfilter_only_fim(mocker):
    """Symmetric case: only ``data_julgamento_fim`` is set."""
    mocker.patch("time.sleep")
    _stub_endpoints()

    df = jus.scraper("tjpb").cjsg(
        "dano moral", paginas=1, data_julgamento_fim="31/12/2023"
    )

    assert len(df) == 4  # 1 from 2022 + 3 from 2023
    assert df["data_julgamento"].max() <= date(2023, 12, 31)
    # 2024+ process must be filtered out:
    assert "0820520-14.2024.8.15.0001" not in df["processo"].values


@responses.activate
def test_postfilter_iso_strings(mocker):
    """Refs #195: ISO ``YYYY-MM-DD`` input must trigger the post-filter.

    Before the fix, the local helper only accepted ``DD/MM/YYYY`` and
    silently skipped the filter for ISO inputs.
    """
    mocker.patch("time.sleep")
    _stub_endpoints()

    df = jus.scraper("tjpb").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2025-12-31",
    )

    assert len(df) == 6
    assert df["data_julgamento"].min() >= date(2024, 1, 1)
    assert df["data_julgamento"].max() <= date(2025, 12, 31)


@responses.activate
def test_postfilter_date_objects(mocker):
    """``datetime.date`` instances must also trigger the post-filter."""
    mocker.patch("time.sleep")
    _stub_endpoints()

    df = jus.scraper("tjpb").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio=date(2024, 1, 1),
        data_julgamento_fim=date(2025, 12, 31),
    )

    assert len(df) == 6


@responses.activate
def test_postfilter_no_dates_is_noop(mocker):
    """Without any date filter, the DataFrame must be returned untouched."""
    mocker.patch("time.sleep")
    _stub_endpoints()

    df = jus.scraper("tjpb").cjsg("dano moral", paginas=1)

    assert len(df) == 10  # all hits from the sample
