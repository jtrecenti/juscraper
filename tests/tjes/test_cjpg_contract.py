"""Offline contract tests for TJES cjpg."""
import pandas as pd
import responses

import juscraper as jus
from tests.tjes.test_cjsg_contract import CJSG_MIN_COLUMNS, _add_page


@responses.activate
def test_cjpg_single_page(mocker):
    """First-instance search uses the pje1g core and returns a DataFrame."""
    mocker.patch("time.sleep")
    _add_page(
        "obrigacao de fazer",
        1,
        "cjpg/results_normal_page_01.json",
        core="pje1g",
    )

    df = jus.scraper("tjes").cjpg("obrigacao de fazer", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjpg_no_results(mocker):
    """Zero-result first-instance query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    _add_page(
        "juscraper_probe_zero_hits_xyzqwe",
        1,
        "cjpg/no_results.json",
        core="pje1g",
    )

    df = jus.scraper("tjes").cjpg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
