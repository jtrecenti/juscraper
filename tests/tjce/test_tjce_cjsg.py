"""Integration tests for the TJCE CJSG scraper."""
import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
class TestCJSGTJCE:
    """Tests for TJCE cjsg (jurisprudence)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("tjce")

    def test_busca_simples(self):
        """Simple search returns results."""
        df = self.scraper.cjsg("direito", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_colunas_esperadas(self):
        """Result contains minimum expected columns."""
        df = self.scraper.cjsg("direito", paginas=1)
        colunas_minimas = {"ementa", "processo"}
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
            data_julgamento_inicio="01/01/2024",
            data_julgamento_fim="30/06/2024",
            paginas=1,
        )
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_download_e_parse(self, tmp_path):
        """Download + parse produces same result as cjsg."""
        pasta = self.scraper.cjsg_download(
            "direito", paginas=1, diretorio=str(tmp_path)
        )
        df = self.scraper.cjsg_parse(pasta)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_paginas_int(self):
        """paginas=2 is equivalent to range(1, 3)."""
        df_int = self.scraper.cjsg("direito", paginas=2)
        df_range = self.scraper.cjsg("direito", paginas=range(1, 3))
        assert len(df_int) == len(df_range)
