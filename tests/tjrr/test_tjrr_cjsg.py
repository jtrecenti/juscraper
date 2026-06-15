"""Integration tests for the TJRR scraper."""

import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
class TestCJSGTJRR:
    """Tests for cjsg of TJRR."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("tjrr")

    def test_busca_simples(self):
        """Simple search returns results."""
        df = self.scraper.cjsg("direito", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_colunas_esperadas(self):
        """Result contains expected minimum columns."""
        df = self.scraper.cjsg("direito", paginas=1)
        colunas_minimas = {"processo", "ementa", "relator"}
        assert colunas_minimas.issubset(set(df.columns))

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Paginação do cjsg do TJRR não avança: o backend PrimeFaces ignora "
            "o offset (_first) do datatable e devolve sempre a página 1, mesmo "
            "com o id do componente descoberto dinamicamente (j_idt158) e o "
            "evento de paginação (javax.faces.behavior.event=page) no payload — "
            "verificado ao vivo. O fix do id (camada 1) tornou a resposta AJAX "
            "parseável (antes vinha um blob opaco), mas a navegação de página "
            "(camada 2) continua quebrada no servidor. Fechar exige capturar o "
            "tráfego real de um navegador (HAR). Ver issue de follow-up."
        ),
    )
    def test_paginacao(self):
        """Pagination brings *new* results from page 2, not a re-fetch of page 1.

        Asserting *new* processos (not just a larger count) pins the cursor
        actually advancing — a plain ``len(df_p2) > len(df_p1)`` passes even
        when page 2 merely repeats page 1's rows (which is exactly the current
        TJRR backend behaviour; see the xfail reason).
        """
        df_p1 = self.scraper.cjsg("dano moral", paginas=1)
        df_p2 = self.scraper.cjsg("dano moral", paginas=range(1, 3))
        assert len(df_p2) > len(df_p1)
        novos = set(df_p2["processo"]) - set(df_p1["processo"])
        assert novos, "página 2 não trouxe processos novos (paginação presa)"

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
