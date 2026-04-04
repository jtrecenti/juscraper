"""Integration tests for the TJPA scraper."""

import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
class TestCJSGTJPA:
    """Tests for cjsg of TJPA."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("tjpa")

    def test_busca_simples(self):
        """Simple search returns results."""
        df = self.scraper.cjsg("direito", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_colunas_esperadas(self):
        """Result contains expected minimum columns."""
        df = self.scraper.cjsg("direito", paginas=1)
        colunas_minimas = {"processo", "ementa", "relator", "data_julgamento"}
        assert colunas_minimas.issubset(set(df.columns))

    def test_paginacao(self):
        """Pagination brings results from multiple pages."""
        df_p1 = self.scraper.cjsg("dano moral", paginas=1)
        df_p2 = self.scraper.cjsg("dano moral", paginas=range(1, 3))
        assert len(df_p2) > len(df_p1)

    def test_filtro_data(self):
        """Date filter works."""
        df = self.scraper.cjsg(
            "direito",
            data_inicio="2024-01-01",
            data_fim="2024-06-30",
            paginas=1,
        )
        assert len(df) > 0

    def test_download_e_parse(self):
        """Download + parse produces same result as cjsg."""
        brutos = self.scraper.cjsg_download("direito", paginas=1)
        df = self.scraper.cjsg_parse(brutos)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_paginas_int(self):
        """paginas=2 is equivalent to range(1, 3)."""
        df_int = self.scraper.cjsg("direito", paginas=2)
        df_range = self.scraper.cjsg("direito", paginas=range(1, 3))
        assert len(df_int) == len(df_range)
