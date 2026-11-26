"""Testes offline do parser do ``cjsg`` do TJRN sobre samples reais.

O ``_source`` do Elasticsearch do TJRN nao tem ``relator`` nem
``tipo_decisao``: o parser le ``magistrado`` e ``tipo_teor``. Os samples
``decisoes_*`` trazem um tipo de decisao cada (acordao, monocratica e
sentenca); na sentenca, ``magistrado`` e o juiz de 1o grau.
"""
import json

import pytest

from juscraper.courts.tjrn.parse import cjsg_parse_manager
from tests._helpers import load_sample


@pytest.mark.parametrize("sample", [
    "decisoes_acordao", "decisoes_decisao", "decisoes_sentenca",
    "results_normal_page_01", "results_normal_page_02", "single_page",
])
def test_cjsg_parse_preenche_relator_e_tipo_decisao(sample):
    """``relator`` vem de ``magistrado`` e ``tipo_decisao`` de ``tipo_teor``, linha a linha."""
    bruto = json.loads(load_sample("tjrn", f"cjsg/{sample}.json"))
    fontes = [hit["_source"] for hit in bruto["hits"]["hits"]]

    df = cjsg_parse_manager([bruto])

    assert fontes
    assert df["relator"].tolist() == [f["magistrado"] for f in fontes]
    assert df["tipo_decisao"].tolist() == [f["tipo_teor"] for f in fontes]
    assert df[["relator", "tipo_decisao"]].notna().all().all()
