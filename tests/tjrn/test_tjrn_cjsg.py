"""Integration tests for the TJRN scraper."""

import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
class TestCJSGTJRN:
    """Tests for cjsg of TJRN."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.scraper = jus.scraper("tjrn")

    def test_busca_simples(self):
        """Simple search returns results."""
        df = self.scraper.cjsg("direito", paginas=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_colunas_esperadas(self):
        """Result contains expected minimum columns, with relator and tipo_decisao filled."""
        df = self.scraper.cjsg("direito", paginas=1)
        colunas_minimas = {"processo", "ementa", "relator", "tipo_decisao"}
        assert colunas_minimas.issubset(set(df.columns))
        assert df["relator"].notna().all()
        assert set(df["tipo_decisao"]) <= {"Acórdão", "Decisão", "Sentença"}

    def test_paginacao(self):
        """Pagination brings results from multiple pages."""
        df_p1 = self.scraper.cjsg("dano moral", paginas=1)
        df_p2 = self.scraper.cjsg("dano moral", paginas=range(1, 3))
        assert len(df_p2) > len(df_p1)

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

    @pytest.mark.parametrize(
        ("decisoes", "pesquisa"),
        [("Acórdão", "dano moral"), ("Decisão", ""), ("Sentença", "")],
    )
    def test_filtro_decisoes_traz_so_o_tipo_pedido(self, decisoes, pesquisa):
        """Cada valor de ``decisoes`` traz resultados, todos do tipo pedido.

        O tipo vem em ``tipo_teor`` na resposta bruta. Monocraticas e sentencas
        nao tem ementa, onde ``pesquisa`` busca: vao sem termo, por periodo.
        """
        brutos = self.scraper.cjsg_download(
            pesquisa,
            paginas=1,
            decisoes=decisoes,
            data_julgamento_inicio="2026-11-01",
            data_julgamento_fim="2026-11-20",
        )
        hits = brutos[0]["hits"]["hits"]
        assert hits
        assert {h["_source"]["tipo_teor"] for h in hits} == {decisoes}

    @pytest.mark.parametrize("jurisdicoes", ["TJ", "TR"])
    def test_filtro_jurisdicoes_traz_so_a_jurisdicao_pedida(self, jurisdicoes):
        """Cada valor de ``jurisdicoes`` traz so colegiados da jurisdicao pedida.

        ``"TJ"`` traz orgaos do Tribunal de Justica e ``"TR"``, Turmas Recursais
        e Turma de Uniformizacao; a jurisdicao e conferida pelo ``colegiado``.
        """
        df = self.scraper.cjsg("dano moral", paginas=1, jurisdicoes=jurisdicoes)
        colegiados = df["colegiado"].dropna()
        assert len(colegiados) > 0
        assert all(("Turma" in c) == (jurisdicoes == "TR") for c in colegiados)

    @pytest.mark.parametrize("jurisdicoes", ["TJ", "TR"])
    def test_filtro_jurisdicoes_com_primeiro_grau_volta_vazio(self, jurisdicoes):
        """``jurisdicoes`` com ``grau="1"`` volta sem resultados e sem erro.

        ``"TJ"`` e ``"TR"`` so cobrem o 2o grau. Vai sem termo, por periodo,
        porque decisoes de 1o grau nao tem ementa, onde ``pesquisa`` busca.
        """
        brutos = self.scraper.cjsg_download(
            "",
            paginas=1,
            jurisdicoes=jurisdicoes,
            grau="1",
            data_julgamento_inicio="2026-11-01",
            data_julgamento_fim="2026-11-20",
        )
        assert brutos[0]["hits"]["hits"] == []

    def test_inteiro_teor_busca_termo_em_sentencas(self):
        """Termo no inteiro teor traz sentencas, que nao tem ementa.

        Com o mesmo termo buscado na ementa (default), a busca de sentencas
        volta vazia. O tipo vem em ``tipo_teor`` na resposta bruta.
        """
        brutos = self.scraper.cjsg_download(
            "dano moral", paginas=1, buscar_em="inteiro_teor", decisoes="Sentença",
        )
        hits = brutos[0]["hits"]["hits"]
        assert hits
        assert {h["_source"]["tipo_teor"] for h in hits} == {"Sentença"}
        na_ementa = self.scraper.cjsg_download("dano moral", paginas=1, decisoes="Sentença")
        assert na_ementa[0]["hits"]["total"] == 0
