"""Granular unit tests for TJBA cjsg_parse defensive null handling."""
import pandas as pd

from juscraper.courts.tjba.parse import cjsg_parse


def test_parse_handles_null_decisoes_at_innermost_level():
    """``decisoes: null`` must be treated as an empty list, not iterated over."""
    page = {"data": {"filter": {"decisoes": None}}}
    df = cjsg_parse([page])
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_parse_handles_null_filter_container():
    """``filter: null`` (mirrors TJMT's AcordaoCollection: null pattern) must not raise."""
    page = {"data": {"filter": None}}
    df = cjsg_parse([page])
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_parse_handles_null_data_container():
    """``data: null`` (GraphQL error fallback) must not raise."""
    page = {"data": None}
    df = cjsg_parse([page])
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_parse_handles_empty_page_dict():
    """Completely empty response dict must not raise."""
    df = cjsg_parse([{}])
    assert isinstance(df, pd.DataFrame)
    assert df.empty
