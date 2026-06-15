"""Testes de contrato (offline) das arvores de selecao eSAJ.

Mocka os endpoints ``*TreeSelect.do`` com ``responses`` e valida:

* o roteamento de URL por (metodo, grau) — stem certo (plural no cjsg,
  singular no cjpg) e ``campoId`` correto;
* o contrato do DataFrame retornado (colunas canonicas, nao-vazio);
* a decodificacao UTF-8 (nome acentuado sobrevive);
* os ``ValueError`` para arvores inexistentes no tribunal;
* que os eSAJ-puros nao expoem as arvores de 1o grau (cjpg so existe no TJSP).

Refs #228.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample_bytes

ARVORE_COLUNAS = {"id", "nome", "id_pai", "nivel", "selecionavel", "caminho"}
BASE = "https://esaj.tjsp.jus.br"

# (label, chamada, path relativo, campoId esperado)
CASOS = [
    ("classes_2", lambda s: s.listar_classes(), "cjsg/classesTreeSelect.do", "classes"),
    ("assuntos_2", lambda s: s.listar_assuntos(), "cjsg/assuntosTreeSelect.do", "assuntos"),
    ("orgaos_2", lambda s: s.listar_orgaos(), "cjsg/secaoTreeSelect.do", "secoes"),
    ("classes_1", lambda s: s.listar_classes(grau="1"), "cjpg/classeTreeSelect.do", "classes"),
    ("assuntos_1", lambda s: s.listar_assuntos(grau="1"), "cjpg/assuntoTreeSelect.do", "assuntos"),
    ("varas_1", lambda s: s.listar_varas(), "cjpg/varasTreeSelect.do", "varas"),
]


@pytest.mark.parametrize("label,chamada,path,campo_id", CASOS, ids=[c[0] for c in CASOS])
@responses.activate
def test_roteamento_e_contrato(label, chamada, path, campo_id):
    responses.add(
        responses.GET,
        f"{BASE}/{path}",
        body=load_sample_bytes("tjsp", "arvore/classes_min.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"campoId": campo_id})],
    )
    df = chamada(jus.scraper("tjsp"))

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert set(df.columns) == ARVORE_COLUNAS
    # UTF-8: nome acentuado preservado.
    assert "Medidas Protetivas - Criança e Adolescente (Lei 13.431)" in set(df["nome"])
    # Bateu exatamente no endpoint esperado.
    assert path in responses.calls[0].request.url


@responses.activate
def test_orgaos_nao_existe_no_1o_grau():
    with pytest.raises(ValueError, match="orgaos_1"):
        jus.scraper("tjsp").listar_orgaos(grau="1")
    # Nenhuma requisicao deve ter saido.
    assert len(responses.calls) == 0


def test_esaj_puro_nao_tem_arvore_de_1o_grau():
    tjam = jus.scraper("tjam")
    # cjpg so existe no TJSP: o eSAJ-puro nem expoe ``listar_varas``...
    assert not hasattr(tjam, "listar_varas")
    # ...e pedir 1o grau das arvores compartilhadas levanta ValueError.
    with pytest.raises(ValueError, match="classes_1"):
        tjam.listar_classes(grau="1")
