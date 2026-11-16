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


def test_baixar_inteiro_teor_ao_vivo(tse, tmp_path):
    # Dois pedidos seguidos: o segundo só passa se o intervalo do raspador valer.
    for codigo in (2972172, 3522031):
        caminho = Path(tse.baixar_inteiro_teor(codigo, diretorio=str(tmp_path)))
        conteudo = caminho.read_bytes()
        assert conteudo.startswith(b"%PDF-")
        assert conteudo.rstrip().endswith(b"%%EOF")
