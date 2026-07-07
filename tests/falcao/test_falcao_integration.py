"""Testes de integracao (rede real) para o agregador Falcao.

Rodam so com ``pytest -m integration``. O backend impoe rate limit
(~50 req/janela) e so libera paginas de tamanho 5 ou 10 para usuario nao
autenticado, entao estes testes usam ``paginas=1`` e ``sleep_time`` folgado.
"""
import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
class TestFalcaoIntegration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("falcao", verbose=0, sleep_time=1.5)

    def test_busca_simples(self):
        df = self.scraper.cjsg("dano moral", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert {"processo", "colecao", "tribunal"}.issubset(df.columns)
        assert (df["colecao"] == "acordaos").all()

    def test_ementa_presente_em_acordaos(self):
        df = self.scraper.cjsg("dano moral", paginas=1)
        assert "ementa" in df.columns
        assert df["ementa"].notna().any()

    @pytest.mark.parametrize(
        "colecao",
        ["sentencas", "decisoesmonocraticas", "precedentes", "recursorevista"],
    )
    def test_outras_colecoes(self, colecao):
        df = self.scraper.cjsg("trabalho", paginas=1, colecao=colecao)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert (df["colecao"] == colecao).all()

    def test_filtro_tribunal(self):
        df = self.scraper.cjsg("recurso", paginas=1, tribunais="TST")
        assert len(df) > 0
        assert (df["tribunal"] == "TST").all()

    def test_filtro_data_juntada(self):
        df = self.scraper.cjsg(
            "trabalho",
            paginas=1,
            data_juntada_inicio="2023-01-01",
            data_juntada_fim="2023-01-31",
        )
        assert len(df) > 0

    def test_paginacao_tamanho_10(self):
        df = self.scraper.cjsg("dano moral", paginas=1, tamanho_pagina=10)
        assert len(df) == 10

    def test_download_e_parse(self, tmp_path):
        pasta = self.scraper.cjsg_download(
            "dano moral", paginas=1, diretorio=str(tmp_path)
        )
        df = self.scraper.cjsg_parse(pasta)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
