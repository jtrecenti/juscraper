"""Testes de ``juscraper.core.parse_utils``."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from juscraper.core.parse_utils import clean_html, coerce_date_columns


class TestCleanHtml:
    def test_remove_tags(self):
        assert clean_html("<p>texto</p>") == "texto"

    def test_decode_named_entities(self):
        assert clean_html("&Aacute;gua &amp; fogo") == "Água & fogo"

    def test_decode_numeric_entities(self):
        assert clean_html("&#193;gua &#x41;") == "Água A"

    def test_no_entities_flag(self):
        assert clean_html("&amp; texto", decode_entities=False) == "&amp; texto"

    def test_no_entities_flag_with_tags(self):
        assert clean_html("<p>&amp; texto</p>", decode_entities=False) == "&amp; texto"

    def test_none_passthrough(self):
        assert clean_html(None) is None

    def test_empty_string_passthrough(self):
        assert clean_html("") == ""

    def test_collapse_whitespace(self):
        assert clean_html("<p>a\n\n  b</p>") == "a b"

    def test_combined_tags_and_entities(self):
        result = clean_html("<b>R$&nbsp;1.000</b>")
        assert result == "R$ 1.000"


class TestCoerceDateColumns:
    def test_empty_df_no_raise(self):
        df = pd.DataFrame()
        out = coerce_date_columns(df, ["data_julgamento"])
        assert out.empty

    def test_iso_format(self):
        df = pd.DataFrame({"data_julgamento": ["2024-01-15", "2024-02-20"]})
        coerce_date_columns(df, ["data_julgamento"])
        assert df["data_julgamento"].tolist() == [dt.date(2024, 1, 15), dt.date(2024, 2, 20)]

    def test_none_to_nat(self):
        df = pd.DataFrame({"data_julgamento": [None, "2024-01-15"]})
        coerce_date_columns(df, ["data_julgamento"])
        assert pd.isna(df["data_julgamento"].iloc[0])
        assert df["data_julgamento"].iloc[1] == dt.date(2024, 1, 15)

    def test_missing_columns_silent_noop(self):
        df = pd.DataFrame({"foo": [1, 2]})
        out = coerce_date_columns(df, ["data_julgamento", "data_publicacao"])
        assert list(out.columns) == ["foo"]
        assert out["foo"].tolist() == [1, 2]

    def test_returns_same_df(self):
        df = pd.DataFrame({"data_julgamento": ["2024-01-15"]})
        out = coerce_date_columns(df, ["data_julgamento"])
        assert out is df

    def test_multiple_columns(self):
        df = pd.DataFrame({
            "data_julgamento": ["2024-01-15"],
            "data_publicacao": ["2024-01-20"],
            "outra": ["x"],
        })
        coerce_date_columns(df, ["data_julgamento", "data_publicacao"])
        assert df["data_julgamento"].iloc[0] == dt.date(2024, 1, 15)
        assert df["data_publicacao"].iloc[0] == dt.date(2024, 1, 20)
        assert df["outra"].iloc[0] == "x"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
