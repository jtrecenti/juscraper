"""Testes de integracao (live) das arvores de selecao eSAJ.

Batem nos endpoints reais ``*TreeSelect.do``. Excluidos por padrao; rode com
``pytest -m integration -k arvore``. Usam so as arvores menores (classes do
TJSP e de um eSAJ-puro) para nao baixar os 3-5 MB de assuntos/varas. Refs #228.
"""
import pytest

import juscraper as jus

ARVORE_COLUNAS = {"id", "nome", "id_pai", "nivel", "selecionavel", "caminho"}


@pytest.mark.integration
def test_tjsp_listar_classes_live():
    df = jus.scraper("tjsp").listar_classes()
    assert set(df.columns) == ARVORE_COLUNAS
    assert len(df) > 50
    assert df["selecionavel"].sum() > 0
    # Raiz acentuada confirma a decodificacao UTF-8 ponta a ponta.
    raizes = set(df.loc[df["id_pai"].isna(), "nome"])
    assert any("Í" in nome or "Ã" in nome for nome in raizes)


@pytest.mark.integration
def test_tjsp_listar_classes_primeiro_grau_live():
    df = jus.scraper("tjsp").listar_classes(grau="1")
    assert set(df.columns) == ARVORE_COLUNAS
    assert len(df) > 50


@pytest.mark.integration
def test_esaj_puro_listar_classes_live():
    df = jus.scraper("tjam").listar_classes()
    assert set(df.columns) == ARVORE_COLUNAS
    assert len(df) > 10
