"""Testes offline do parser do ``cjsg`` do TJRN sobre samples reais.

O ``_source`` do Elasticsearch do TJRN nao tem ``relator`` nem
``tipo_decisao``: o parser le ``magistrado`` e ``tipo_teor``. Ha um sample por
tipo de decisao (acordao, monocratica e sentenca), gravados por
``tests/fixtures/capture/tjrn.py``.
"""
import json

import pytest

from juscraper.courts.tjrn.parse import cjsg_parse_manager
from tests._helpers import load_sample

# (sample, valor esperado de ``tipo_decisao`` em todas as linhas)
_CASOS = [
    ("cjsg/decisoes_acordao.json", "Acórdão"),
    ("cjsg/decisoes_decisao.json", "Decisão"),
    ("cjsg/decisoes_sentenca.json", "Sentença"),
]


@pytest.mark.parametrize(("sample", "tipo"), _CASOS, ids=[c[1] for c in _CASOS])
def test_cjsg_parse_preenche_tipo_decisao_e_relator(sample, tipo):
    """``tipo_decisao`` vem de ``tipo_teor`` e ``relator`` de ``magistrado``, linha a linha."""
    bruto = json.loads(load_sample("tjrn", sample))
    fontes = [hit["_source"] for hit in bruto["hits"]["hits"]]
    assert fontes

    df = cjsg_parse_manager([bruto])

    assert df["tipo_decisao"].tolist() == [tipo] * len(fontes)
    assert df["relator"].tolist() == [f["magistrado"] for f in fontes]
    assert df["relator"].notna().all()


def test_cjsg_parse_sentenca_traz_juiz_de_primeiro_grau_em_relator():
    """Na sentenca, ``relator`` e o juiz de 1o grau, como no ``cjpg`` do eSAJ."""
    bruto = json.loads(load_sample("tjrn", "cjsg/decisoes_sentenca.json"))

    df = cjsg_parse_manager([bruto])

    primeira = bruto["hits"]["hits"][0]["_source"]
    assert primeira["grau"] == 1
    assert df.loc[0, "relator"] == primeira["magistrado"]
    assert df.loc[0, "orgao_julgador"] == primeira["orgao_julgador"]


@pytest.mark.parametrize(
    "sample",
    ["cjsg/results_normal_page_01.json", "cjsg/results_normal_page_02.json", "cjsg/single_page.json"],
)
def test_cjsg_parse_busca_sem_filtro_preenche_tipo_decisao_e_relator(sample):
    """Nos samples da busca sem filtro de tipo, as duas colunas tambem vem preenchidas."""
    df = cjsg_parse_manager([json.loads(load_sample("tjrn", sample))])

    assert len(df) > 0
    assert df["tipo_decisao"].notna().all()
    assert df["relator"].notna().all()
