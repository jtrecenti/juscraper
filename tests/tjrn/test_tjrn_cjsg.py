"""Integration tests for the TJRN scraper."""

import pandas as pd
import pytest

import juscraper as jus
from juscraper.courts.tjrn.client import _to_tjrn_date
from juscraper.courts.tjrn.download import BASE_URL, build_cjsg_payload


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
        ("decisoes", "pesquisa", "filtros"),
        [
            ("Acórdão", "dano moral", {}),
            ("Decisão", "", {}),
            ("Sentença", "", {}),
            ("Sentença", "", {"grau": "1"}),
            ("Decisão", "", {"grau": "1"}),
            ("Decisão", "", {"jurisdicoes": "TJ"}),
            ("Decisão", "", {"jurisdicoes": "TR"}),
        ],
    )
    def test_filtro_decisoes_traz_so_o_tipo_pedido(self, decisoes, pesquisa, filtros):
        """Cada valor de ``decisoes`` traz resultados, todos do tipo pedido.

        O tipo vem em ``tipo_teor`` na resposta bruta. Monocraticas e sentencas
        nao tem ementa, onde ``pesquisa`` busca: vao sem termo, por periodo.
        ``filtros`` cobre as combinacoes com grau e jurisdicao que o schema
        aceita: a sentenca no 1o grau e a monocratica nos dois graus.
        """
        brutos = self.scraper.cjsg_download(
            pesquisa,
            paginas=1,
            decisoes=decisoes,
            data_julgamento_inicio="2026-11-01",
            data_julgamento_fim="2026-11-20",
            **filtros,
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
        # Busca na ementa, que so os acordaos tem: "Acórdão" existe nas duas jurisdicoes.
        assert set(df["tipo_decisao"]) == {"Acórdão"}

    @pytest.mark.parametrize(
        "filtros",
        [
            {"jurisdicoes": "TJ", "grau": "1"},
            {"jurisdicoes": "TR", "grau": "1"},
            {"decisoes": "Sentença", "grau": "2"},
            {"decisoes": "Sentença", "jurisdicoes": "TJ"},
            {"decisoes": "Sentença", "jurisdicoes": "TR"},
            {"decisoes": "Acórdão", "grau": "1"},
        ],
    )
    def test_filtros_de_graus_diferentes_voltam_vazios(self, filtros):
        """Filtros de graus diferentes voltam sem resultados no portal.

        E a prova de que ``InputCJSGTJRN`` pode recusar as combinacoes: como a
        API publica levanta ``ValidationError``, o payload vai direto pela
        sessao do scraper, sem passar pelo schema. ``"TJ"``, ``"TR"`` e
        ``"Acórdão"`` so existem no 2o grau, e ``"Sentença"`` so no 1o. Vai sem
        termo, por periodo, porque sentencas e decisoes de 1o grau nao tem
        ementa; o mesmo periodo traz resultados sem o filtro cruzado
        (``test_filtro_decisoes_traz_so_o_tipo_pedido`` e
        ``test_filtro_grau_traz_so_o_grau_pedido``).
        """
        payload = build_cjsg_payload(
            "",
            dt_inicio=_to_tjrn_date("2026-11-01"),
            dt_fim=_to_tjrn_date("2026-11-20"),
            **filtros,
        )
        resp = self.scraper.session.post(BASE_URL, json=payload, timeout=60)
        resp.raise_for_status()
        assert resp.json()["hits"]["hits"] == []

    @pytest.mark.parametrize("sistema", ["PJE", "SAJ"])
    def test_filtro_sistema_traz_so_o_sistema_pedido(self, sistema):
        """Cada valor de ``sistema`` traz so processos do sistema pedido."""
        df = self.scraper.cjsg("dano moral", paginas=1, sistema=sistema)
        assert len(df) > 0
        assert set(df["sistema"]) == {sistema}

    @pytest.mark.parametrize("grau", ["1", "2"])
    def test_filtro_grau_traz_so_o_grau_pedido(self, grau):
        """Cada valor de ``grau`` traz so decisoes do grau pedido.

        Vai sem termo, por periodo, porque decisoes de 1o grau nao tem ementa.
        O backend grava ``grau`` como inteiro no PJe e como texto no SAJ.
        """
        brutos = self.scraper.cjsg_download(
            "",
            paginas=1,
            grau=grau,
            data_julgamento_inicio="2026-11-01",
            data_julgamento_fim="2026-11-20",
        )
        hits = brutos[0]["hits"]["hits"]
        assert hits
        assert {str(h["_source"]["grau"]) for h in hits} == {grau}

    def test_inteiro_teor_busca_termo_em_sentencas(self):
        """Termo no inteiro teor traz sentencas, que nao tem ementa.

        Na ementa (default), a mesma busca dava 0 sentencas em 26/11/2026.
        O tipo vem em ``tipo_teor`` na resposta bruta.
        """
        brutos = self.scraper.cjsg_download(
            "dano moral", paginas=1, buscar_em="inteiro_teor", decisoes="Sentença",
        )
        hits = brutos[0]["hits"]["hits"]
        assert hits
        assert {h["_source"]["tipo_teor"] for h in hits} == {"Sentença"}
