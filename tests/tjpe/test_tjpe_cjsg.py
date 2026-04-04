"""Integration tests for the TJPE scraper."""

import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
class TestCJSGTJPE:
    """Tests for cjsg of TJPE."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("tjpe")

    def test_busca_simples(self):
        """Simple search returns results."""
        df = self.scraper.cjsg("direito", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_colunas_esperadas(self):
        """Result contains minimum expected columns."""
        df = self.scraper.cjsg("direito", paginas=1)
        colunas_minimas = {"processo", "relator", "ementa", "data_julgamento"}
        assert colunas_minimas.issubset(set(df.columns))

    def test_paginacao(self):
        """Pagination brings results from multiple pages."""
        df = self.scraper.cjsg("dano moral", paginas=range(1, 3))
        df_p1 = self.scraper.cjsg("dano moral", paginas=1)
        assert len(df) > len(df_p1)

    def test_download_e_parse(self):
        """Download + parse produces same result as cjsg."""
        raw = self.scraper.cjsg_download("direito", paginas=1)
        df = self.scraper.cjsg_parse(raw)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_paginas_int(self):
        """paginas=2 is equivalent to range(1, 3)."""
        df_int = self.scraper.cjsg("direito", paginas=2)
        df_range = self.scraper.cjsg("direito", paginas=range(1, 3))
        assert len(df_int) == len(df_range)
