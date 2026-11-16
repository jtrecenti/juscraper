"""Testes ao vivo do TSE: catálogos e inteiro teor (precisam de rede)."""
from pathlib import Path

import pytest

import juscraper as jus

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def tse():
    return jus.scraper("tse")


@pytest.mark.parametrize(
    ("metodo", "coluna", "valor"),
    [
        ("listar_classes", "sigla_classe", "RESPE"),
        ("listar_relatores", "relator", "Alexandre de Moraes"),
        ("listar_eleicoes", "eleicao", "2022"),
        ("listar_normas", "sigla", "CE"),
    ],
)
def test_catalogo_ao_vivo(tse, metodo, coluna, valor):
    df = getattr(tse, metodo)()
    assert valor in set(df[coluna])


@pytest.mark.parametrize(
    ("tribunal", "metodo", "coluna", "valor"),
    [
        ("tre-sp", "listar_classes", "sigla_classe", "RE"),
        ("tre-sp", "listar_relatores", "relator", "A. C. Mathias Coltro"),
        ("tres", "listar_eleicoes", "eleicao", "2022"),
        ("tres", "listar_normas", "sigla", "CE"),
    ],
)
def test_catalogo_de_tre_ao_vivo(tse, tribunal, metodo, coluna, valor):
    df = getattr(tse, metodo)(tribunal=tribunal)
    assert valor in set(df[coluna])


def test_baixar_inteiros_teores_ao_vivo(tmp_path):
    # Instância nova de propósito: o intervalo vale entre instâncias, e os
    # dois testes de inteiro teor deste módulo não recusam um ao outro.
    # 3419640 é um acórdão do TRE-RS: o serviço é o mesmo dos TREs. O código 1 não existe.
    with pytest.warns(UserWarning, match="1: nao_pdf"):
        df = jus.scraper("tse").baixar_inteiros_teores([3419640, 1, 3522031], diretorio=str(tmp_path))

    assert df["motivo_falha"].tolist() == [None, "nao_pdf", None]
    for caminho in df["caminho_inteiro_teor"].dropna():
        assert Path(caminho).read_bytes().startswith(b"%PDF-")
    assert df["caminho_inteiro_teor"].isna().tolist() == [False, True, False]


def test_baixar_inteiro_teor_ao_vivo(tse, tmp_path):
    # Dois pedidos seguidos: o segundo só passa se o intervalo do raspador valer.
    for codigo in (2972172, 3522031):
        caminho = Path(tse.baixar_inteiro_teor(codigo, diretorio=str(tmp_path)))
        conteudo = caminho.read_bytes()
        assert conteudo.startswith(b"%PDF-")
        assert conteudo.rstrip().endswith(b"%%EOF")
