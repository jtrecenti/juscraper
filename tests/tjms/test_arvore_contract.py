"""Contrato (offline) das árvores de 1º grau do TJMS (#487).

O formulário do cjpg do TJMS tem as mesmas árvores, nas mesmas rotas, que o
do TJSP (samples ``cjpg/results_normal_page_01.html`` dos dois). Os casos e o
corpo são os do contrato do TJSP: o teste confere o roteamento para o host do
TJMS; a leitura das árvores reais do TJMS está em ``test_cjpg_integration.py``.
"""
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample_bytes
from tests.tjsp.test_arvore_contract import ARVORE_COLUNAS, CASOS

CASOS_1O_GRAU = {label: resto for label, *resto in CASOS if label.endswith("_1")}


@pytest.mark.parametrize(("chamada", "path", "campo_id"), list(CASOS_1O_GRAU.values()), ids=list(CASOS_1O_GRAU))
@responses.activate
def test_pede_as_arvores_de_1o_grau_ao_tjms(chamada, path, campo_id):
    responses.add(
        responses.GET,
        f"https://esaj.tjms.jus.br/{path}",
        body=load_sample_bytes("tjsp", "arvore/classes_min.html"),
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"campoId": campo_id})],
    )
    df = chamada(jus.scraper("tjms"))

    assert set(df.columns) == ARVORE_COLUNAS
    assert not df.empty
