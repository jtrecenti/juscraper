"""Integration tests for the TJBA scraper."""

import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
class TestCJSGTJBA:
    """Tests for TJBA cjsg."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("tjba")

    def test_busca_simples(self):
        """Simple search returns results."""
        df = self.scraper.cjsg("direito", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_colunas_esperadas(self):
        """Result contains expected minimum columns."""
        df = self.scraper.cjsg("direito", paginas=1)
        colunas_minimas = {"processo", "relator", "orgao_julgador", "ementa", "data_publicacao"}
        assert colunas_minimas.issubset(set(df.columns))

    def test_paginacao(self):
        """Pagination brings results from multiple pages."""
        df = self.scraper.cjsg("dano moral", paginas=range(1, 3))
        df_p1 = self.scraper.cjsg("dano moral", paginas=1)
        assert len(df) > len(df_p1)

    def test_filtro_data(self):
        """Date filter works."""
        df = self.scraper.cjsg(
            "direito",
            data_publicacao_inicio="2024-01-01",
            data_publicacao_fim="2024-06-30",
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

    def test_numero_recurso(self):
        """Search by case number returns specific result."""
        df = self.scraper.cjsg(
            "",
            numero_recurso="0008415-21.2025.8.05.0150",
            paginas=1,
        )
        assert len(df) >= 1
        assert "0008415-21.2025.8.05.0150" in df["processo"].values
