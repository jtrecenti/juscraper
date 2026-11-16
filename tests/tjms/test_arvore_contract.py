"""Contrato (offline) das árvores de 1º grau do TJMS (#487).

O formulário do cjpg do TJMS tem as mesmas árvores, nas mesmas rotas, que o
do TJSP (samples ``cjpg/results_normal_page_01.html`` dos dois). Os casos são
os do contrato do TJSP; o corpo de cada árvore é um recorte da resposta real
do TJMS (``samples/arvore/<arvore>_1_min.html``).
"""
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample_bytes
from tests.tjsp.test_arvore_contract import ARVORE_COLUNAS, CASOS

CASOS_1O_GRAU = {label: resto for label, *resto in CASOS if label.endswith("_1")}

# Um nó selecionável de cada recorte: (id, caminho).
NO_ESPERADO = {
    "classes_1": (
        "4082",
        "PROCEDIMENTOS ADMINISTRATIVOS > Procedimento Relativo à Posse de Maconha para Consumo Pessoal",
    ),
    "assuntos_1": ("3903", "DIREITO DO CONSUMIDOR > Superendividamento"),
    # Varas: comarca > foro > vara, com id ``<foro>-<vara>``.
    "varas_1": ("1-14", "Campo Grande > Campo Grande > 14ª Vara Cível"),
}


@pytest.mark.parametrize("label", list(CASOS_1O_GRAU))
@responses.activate
def test_pede_as_arvores_de_1o_grau_ao_tjms(label):
    chamada, path, campo_id = CASOS_1O_GRAU[label]
    responses.add(
        responses.GET,
        f"https://esaj.tjms.jus.br/{path}",
        body=load_sample_bytes("tjms", f"arvore/{label}_min.html"),
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"campoId": campo_id})],
    )
    df = chamada(jus.scraper("tjms"))

    assert set(df.columns) == ARVORE_COLUNAS
    id_, caminho = NO_ESPERADO[label]
    no = df.loc[df["id"] == id_].iloc[0]
    assert no["caminho"] == caminho
    assert no["selecionavel"]
