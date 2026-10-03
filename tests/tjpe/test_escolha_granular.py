"""Caracterização da seleção de botões na página de escolha do TJPE."""

import pytest

from juscraper.courts.tjpe.download import extract_escolha_button_id
from tests._helpers import load_sample


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [("Acórdãos", "primeiro"), ("Decisões Monocráticas", "mono")],
)
def test_escolha_pula_candidatos_invalidos_e_preserva_ordem(tipo, esperado):
    html = load_sample("tjpe", "cjsg/escolha_candidates.html")
    assert extract_escolha_button_id(html, tipo) == esperado


def test_escolha_tipo_padrao():
    html = load_sample("tjpe", "cjsg/escolha_candidates.html")
    assert extract_escolha_button_id(html) == "primeiro"


@pytest.mark.parametrize("tipo", ["acórdãos", "Acórdãos ", "Sentenças"])
def test_escolha_exige_rotulo_exato(tipo):
    html = load_sample("tjpe", "cjsg/escolha_candidates.html")
    with pytest.raises(ValueError) as erro:
        extract_escolha_button_id(html, tipo)
    assert str(erro.value) == f"Could not find escolha button for '{tipo}'"


@pytest.mark.parametrize(
    "conteudo",
    [
        "",
        '<a onclick="\'id\':\'id\'">1 documentos encontrados</a>',
        '<td><a onclick="\'id\':\'id\'">1 documentos encontrados</a></td>',
        '<tr><td>Acórdãos</td><td>{link}</td></tr>',
        '<tr><td><label>Outro</label></td><td><label>Acórdãos</label>{link}</td></tr>',
        '<tr><td><label>Acórdãos</label></td><td><a>1 documentos encontrados</a></td></tr>',
        '<tr><td><label>Acórdãos</label></td><td><a onclick="false">1 documentos encontrados</a></td></tr>',
        '<tr><td><label>Acórdãos</label></td><td><a onclick="\'id\':\'id\'">1 Documentos encontrados</a></td></tr>',
    ],
)
def test_escolha_sem_botao_utilizavel(conteudo):
    link = '<a onclick="\'id\':\'id\'">1 documentos encontrados</a>'
    html = conteudo.replace("{link}", link)
    with pytest.raises(ValueError, match="Could not find escolha button for 'Acórdãos'"):
        extract_escolha_button_id(html)


def test_escolha_tipo_vazio_aceita_linha_sem_label():
    html = '<tr><td>Sem label</td><td><a onclick="\'id\':\'id\'">1 documentos encontrados</a></td></tr>'
    assert extract_escolha_button_id(html, "") == "id"
