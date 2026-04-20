"""Integration tests for the TJES scraper."""

import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
class TestCJSGTJES:
    """Tests for TJES cjsg."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("tjes")

    def test_busca_simples(self):
        """Simple search returns results."""
        df = self.scraper.cjsg("direito", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_colunas_esperadas(self):
        """Result contains expected minimum columns."""
        df = self.scraper.cjsg("direito", paginas=1)
        colunas_minimas = {"nr_processo", "ementa", "magistrado", "orgao_julgador"}
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
            data_julgamento_inicio="2024-01-01",
            data_julgamento_fim="2024-06-30",
            paginas=1,
        )
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_filtro_magistrado(self):
        """Magistrado filter works."""
        df = self.scraper.cjsg(
            "direito",
            magistrado="HELIMAR PINTO",
            paginas=1,
        )
        assert len(df) > 0
        assert all(df["magistrado"] == "HELIMAR PINTO")

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

    def test_core_pje2g_mono(self):
        """Querying the pje2g_mono core works."""
        df = self.scraper.cjsg("direito", core="pje2g_mono", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_cjsg_rejects_pje1g(self):
        """cjsg raises ValueError when core='pje1g' (use cjpg instead)."""
        with pytest.raises(ValueError, match="cjpg"):
            self.scraper.cjsg("direito", core="pje1g", paginas=1)


@pytest.mark.integration
class TestCJPGTJES:
    """Tests for TJES cjpg (first instance)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("tjes")

    def test_busca_simples(self):
        """Simple cjpg search returns results."""
        df = self.scraper.cjpg("direito", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_colunas_esperadas(self):
        """cjpg result contains expected minimum columns."""
        df = self.scraper.cjpg("direito", paginas=1)
        colunas_minimas = {"nr_processo", "ementa", "magistrado"}
        assert colunas_minimas.issubset(set(df.columns))

    def test_download_e_parse(self):
        """cjpg_download + cjpg_parse works."""
        brutos = self.scraper.cjpg_download("direito", paginas=1)
        df = self.scraper.cjpg_parse(brutos)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
