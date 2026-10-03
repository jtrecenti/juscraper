"""Caracteriza o corpo STF sem usar o próprio construtor como expectativa."""

import copy
import itertools

import pytest

from juscraper.courts.stf.download import build_payload


@pytest.mark.parametrize("base", ["decisoes", "acordaos"])
@pytest.mark.parametrize("limites", list(itertools.product([None, "01012024"], repeat=4)))
def test_combina_limites_de_data_sem_alterar_outros_filtros(base, limites):
    julgamento_inicio, julgamento_fim, publicacao_inicio, publicacao_fim = limites
    original = build_payload(base=base)
    corpo = build_payload(
        base=base,
        data_julgamento_inicio=julgamento_inicio,
        data_julgamento_fim=julgamento_fim,
        data_publicacao_inicio=publicacao_inicio,
        data_publicacao_fim=publicacao_fim,
    )
    esperado = copy.deepcopy(original)
    filtros = esperado["query"]["function_score"]["query"]["bool"]["filter"]
    for campo, inicio, fim in (
        ("julgamento_data", julgamento_inicio, julgamento_fim),
        ("publicacao_data", publicacao_inicio, publicacao_fim),
    ):
        if inicio is None and fim is None:
            continue
        faixa = {"format": "ddMMyyyy"}
        if inicio is not None:
            faixa["from"] = inicio
        if fim is not None:
            faixa["lte"] = fim
        filtros.append({"range": {campo: faixa}})
    assert corpo == esperado
    assert build_payload(base=base) == original


@pytest.mark.parametrize("base", ["decisoes", "acordaos"])
@pytest.mark.parametrize("classe", [None, "", [], "Rcl", ["Rcl", "ADI", "Rcl"]])
def test_filtro_de_classe_preserva_faceta_propria_e_demais_agregacoes(base, classe):
    original = build_payload(base=base)
    corpo = build_payload(base=base, classe=classe)
    if not classe:
        assert corpo == original
        return
    valores = [classe] if isinstance(classe, str) else classe
    filtro = {"terms": {"processo_classe_processual_unificada_classe_sigla.keyword": valores}}
    esperado = copy.deepcopy(original)
    esperado["post_filter"]["bool"]["must"].append(filtro)
    for nome, agregacao in original["aggs"].items():
        if nome == "processo_classe_processual_unificada_classe_sigla_agg":
            continue
        if "filter" in agregacao:
            esperado["aggs"][nome]["filter"]["bool"]["must"].append(filtro)
        else:
            esperado["aggs"][nome] = {"filter": {"bool": {"must": [filtro]}}, "aggs": {nome: agregacao}}
    assert corpo == esperado
    assert build_payload(base=base) == original


@pytest.mark.parametrize("base", ["decisoes", "acordaos"])
def test_consulta_e_reforcos_recebem_mesmo_texto_com_pesos_distintos(base):
    original = build_payload(base=base)
    corpo = build_payload('saúde e "não"', base=base, inteiro_teor=True, reference_time="2024-01-01T00:00:00Z")
    consulta = corpo["query"]["function_score"]["query"]["bool"]
    clausulas = [consulta["filter"][0]["query_string"], *[item["query_string"] for item in consulta["should"]]]
    assert [item["query"] for item in clausulas] == ['saúde AND "não"'] * 5
    assert [item["fields"][-1] for item in clausulas[:3]] == [
        "inteiro_teor_texto.plural", "inteiro_teor_texto.plural", "inteiro_teor_texto.plural^0.5",
    ]
    assert [item["fields"] for item in clausulas[3:]] == [
        item["query_string"]["fields"]
        for item in original["query"]["function_score"]["query"]["bool"]["should"][2:]
    ]
    assert corpo["query"]["function_score"]["functions"][0]["exp"]["julgamento_data"]["origin"] == (
        "2024-01-01T00:00:00Z"
    )
    assert build_payload(base=base) == original


@pytest.mark.parametrize(
    ("pagina", "tamanho", "inicio", "quantidade"),
    [(1429, 7, 9996, 4), (10000, 1, 9999, 1), (99999, 0, 0, 0)],
)
def test_limite_de_resultados_e_consulta_de_contagem(pagina, tamanho, inicio, quantidade):
    corpo = build_payload(pagina=pagina, tamanho_pagina=tamanho)
    assert (corpo["from"], corpo["size"]) == (inicio, quantidade)


def test_rejeita_pagina_fora_do_limite_antes_de_ler_base():
    with pytest.raises(ValueError, match="pagina 1001 com 10 por pagina comeca no registro 10001"):
        build_payload(base="inexistente", pagina=1001)
