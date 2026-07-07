"""Granular tests (offline) para helpers do agregador Falcao."""
import json

import pytest

from juscraper.aggregators.falcao.client import FalcaoScraper
from juscraper.aggregators.falcao.download import build_pesquisa_params, gerar_session_id
from juscraper.aggregators.falcao.parse import parse_documentos, parse_total
from tests._helpers import load_sample


def _sample(colecao: str) -> dict:
    return json.loads(load_sample("falcao", f"pesquisa/{colecao}_normal.json"))


def test_gerar_session_id_formato():
    sid = gerar_session_id()
    assert sid.startswith("_")
    assert len(sid) == 8
    assert sid[1:].isalnum()


def test_build_params_pagina_1based_para_0based():
    p = build_pesquisa_params(
        pesquisa="x", colecao="acordaos", session_id="_a", pagina=1
    )
    assert p["page"] == 0
    p3 = build_pesquisa_params(
        pesquisa="x", colecao="acordaos", session_id="_a", pagina=3
    )
    assert p3["page"] == 2


def test_build_params_lista_vira_csv():
    p = build_pesquisa_params(
        pesquisa="x", colecao="acordaos", session_id="_a", pagina=1,
        relator=["A", "B"], tribunais="TST",
    )
    assert p["nomeRelator"] == "A,B"
    assert p["tribunais"] == "TST"


def test_build_params_omite_filtros_none():
    p = build_pesquisa_params(
        pesquisa="x", colecao="acordaos", session_id="_a", pagina=1
    )
    assert "nomeRelator" not in p
    assert "dataInicio" not in p
    assert "temEmenta" not in p


def test_parse_total_le_quantidade():
    assert parse_total(_sample("acordaos")) == 10000


def test_parse_total_sem_chave_levanta():
    with pytest.raises(ValueError):
        parse_total({"documentos": []})


def test_parse_documentos_renomeia_processo_e_datas():
    docs = parse_documentos(_sample("acordaos"), "acordaos")
    d = docs[0]
    assert "numeroProcesso" not in d  # renomeado
    assert d["processo"]
    assert "dataJulgamento" not in d and "data_julgamento" in d
    assert "dataJuntada" not in d and "data_juntada" in d
    assert d["colecao"] == "acordaos"


def test_parse_documentos_precedentes_usa_numero_como_processo():
    docs = parse_documentos(_sample("precedentes"), "precedentes")
    # precedentes nao tem numeroProcesso — cai no 'numero'
    assert docs[0]["processo"] == docs[0].get("numero")


def test_parse_documentos_relator_de_nomerelator():
    # sentencas usam nomeRelator; parser deve preencher 'relator'
    docs = parse_documentos(_sample("sentencas"), "sentencas")
    assert docs[0].get("relator") == docs[0].get("nomeRelator")


@pytest.mark.parametrize(
    "total,tamanho,esperado",
    [(0, 10, 1), (5, 10, 1), (10, 10, 1), (11, 10, 2), (95, 10, 10),
     (999999, 10, 1000), (999999, 5, 2000)],
)
def test_total_paginas_respeita_teto(total, tamanho, esperado):
    # teto do backend = 10000 resultados
    assert FalcaoScraper._total_paginas(total, tamanho) == esperado


@pytest.mark.parametrize(
    "paginas,total_pags,esperado",
    [
        (None, 3, [1, 2, 3]),
        (range(1, 10), 3, [1, 2, 3]),
        (range(2, 5), 10, [2, 3, 4]),
        ([1, 5, 99], 4, [1]),
    ],
)
def test_resolver_paginas(paginas, total_pags, esperado):
    assert list(FalcaoScraper._resolver_paginas(paginas, total_pags)) == esperado
