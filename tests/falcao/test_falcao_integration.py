"""Testes de integracao (rede real) para o agregador Falcao.

Rodam so com ``pytest -m integration``. O backend impoe rate limit por IP e,
estourada a janela, bloqueia por horas (429 com
``x-rate-limit-retry-after-seconds``); so libera paginas de tamanho 5 ou 10
para usuario nao autenticado. Por isso estes testes usam ``paginas=1`` e
``sleep_time`` folgado. O marker ``anti_bot`` converte o bloqueio do WAF
(CloudFront) em xfail, porque ele depende do IP do cliente.
"""
import pandas as pd
import pytest

import juscraper as jus

pytestmark = [pytest.mark.integration, pytest.mark.anti_bot]


class TestFalcaoIntegration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("falcao", verbose=0, sleep_time=1.5)

    def test_busca_simples(self):
        df = self.scraper.cjsg("dano moral", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert {"processo", "colecao", "tribunal", "classe_sigla"}.issubset(df.columns)
        assert (df["colecao"] == "acordaos").all()
        assert not [c for c in df.columns if c.startswith("highlight")]

    def test_ementa_presente_e_sem_html_em_acordaos(self):
        df = self.scraper.cjsg("dano moral", paginas=1)
        ementas = df["ementa"].dropna()
        assert len(ementas) > 0
        assert not ementas.str.contains(r"<\w+[^>]*>", regex=True).any()

    @pytest.mark.parametrize(
        "colecao",
        ["sentencas", "decisoesmonocraticas", "precedentes", "recursorevista"],
    )
    def test_outras_colecoes(self, colecao):
        df = self.scraper.cjsg("trabalho", paginas=1, colecao=colecao)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert (df["colecao"] == colecao).all()
        assert df["processo"].notna().all()
        assert df["processo"].is_unique

    @pytest.mark.parametrize("colecao", ["sentencas", "decisoesmonocraticas"])
    def test_relator_preenchido_em_juiz_singular(self, colecao):
        df = self.scraper.cjsg("horas extras", paginas=1, colecao=colecao)
        assert df["relator"].notna().all()
        assert (df["relator"] != "").all()

    def test_classe_sigla_serve_de_filtro(self):
        df = self.scraper.cjsg("horas extras", paginas=1, colecao="sentencas")
        sigla = df["classe_sigla"].dropna().iloc[0]
        filtrado = self.scraper.cjsg("horas extras", paginas=1, colecao="sentencas", classe=sigla)
        assert len(filtrado) > 0
        assert (filtrado["classe_sigla"] == sigla).all()

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
