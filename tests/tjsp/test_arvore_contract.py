"""Testes de contrato (offline) das arvores de selecao eSAJ.

Mocka os endpoints ``*TreeSelect.do`` com ``responses`` e valida:

* o roteamento de URL por (metodo, grau) — stem certo (plural no cjsg,
  singular no cjpg) e ``campoId`` correto;
* o contrato do DataFrame retornado (colunas canonicas e um no real do
  recorte de cada arvore, em ``samples/arvore/<arvore>_min.html``);
* a decodificacao UTF-8 (nome acentuado sobrevive);
* os ``ValueError`` para arvores inexistentes no tribunal;
* que os eSAJ-puros nao expoem as arvores de 1o grau (cjpg so no TJSP e no TJMS).

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


# Um nó selecionável de cada recorte ``samples/arvore/<label>_min.html``,
# com acento no caminho para conferir a decodificação UTF-8: (id, caminho).
NO_ESPERADO = {
    "classes_2": (
        "14734",
        "PROCESSO CRIMINAL > Medidas Cautelares > Medidas Protetivas - Criança e Adolescente (Lei 13.431)",
    ),
    "assuntos_2": ("0", "0 - Assunto não Especificado - Cível"),
    "orgaos_2": ("0-434", "DIREITO PÚBLICO > 1.ª Câmara Direito Público B"),
    "classes_1": ("3703", "JUIZADOS DA INFÂNCIA E DA JUVENTUDE > Seção Administrativa > Inspeção"),
    "assuntos_1": ("5238", "DIREITO CIVIL > Direitos da Personalidade"),
    # Varas: comarca > foro > vara, com id ``<foro>-<vara>``.
    "varas_1": ("81-6570", "Adamantina > Foro de Adamantina > 1ª. Vara Judicial"),
}


@pytest.mark.parametrize("label,chamada,path,campo_id", CASOS, ids=[c[0] for c in CASOS])
@responses.activate
def test_roteamento_e_contrato(label, chamada, path, campo_id):
    responses.add(
        responses.GET,
        f"{BASE}/{path}",
        body=load_sample_bytes("tjsp", f"arvore/{label}_min.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"campoId": campo_id})],
    )
    df = chamada(jus.scraper("tjsp"))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == ARVORE_COLUNAS
    id_, caminho = NO_ESPERADO[label]
    no = df.loc[df["id"] == id_].iloc[0]
    assert no["caminho"] == caminho
    assert no["selecionavel"]
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
    # cjpg so no TJSP e no TJMS: o eSAJ-puro nem expoe ``listar_varas``...
    assert not hasattr(tjam, "listar_varas")
    # ...e pedir 1o grau das arvores compartilhadas levanta ValueError.
    with pytest.raises(ValueError, match="classes_1"):
        tjam.listar_classes(grau="1")
