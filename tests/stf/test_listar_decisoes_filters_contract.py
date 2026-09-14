"""Filter propagation, deprecated aliases and payload shape for STF listar_decisoes."""
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.stf.download import BASE_URL, build_payload, traduzir_operadores
from tests._helpers import load_sample

PESQUISA = "juscraper_probe_zero_hits_xyzqwe"


def _add_no_results(**payload_kwargs) -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("stf", "listar_decisoes/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_payload(**payload_kwargs))],
    )


@pytest.fixture
def stf():
    return jus.scraper("stf", waf_token="token-de-teste")


@responses.activate
def test_todos_os_filtros_chegam_ao_corpo(stf, mocker):
    mocker.patch("time.sleep")
    _add_no_results(
        pesquisa=PESQUISA,
        pagina=1,
        tamanho_pagina=100,
        base="acordaos",
        classe=["Rcl", "ARE"],
        inteiro_teor=True,
        data_julgamento_inicio="01012024",
        data_julgamento_fim="31122024",
        data_publicacao_inicio="01022024",
        data_publicacao_fim="30112024",
    )

    stf.listar_decisoes(
        PESQUISA,
        paginas=1,
        tamanho_pagina=100,
        base="acordaos",
        classe=["Rcl", "ARE"],
        inteiro_teor=True,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
        data_publicacao_inicio="01/02/2024",
        data_publicacao_fim="30/11/2024",
    )

    assert len(responses.calls) == 1


@responses.activate
def test_alias_query_vira_pesquisa(stf, mocker):
    mocker.patch("time.sleep")
    _add_no_results(pesquisa=PESQUISA, pagina=1, tamanho_pagina=250)

    with pytest.warns(DeprecationWarning):
        stf.listar_decisoes(query=PESQUISA, paginas=1)


@responses.activate
def test_alias_data_inicio_fim_vira_data_julgamento(stf, mocker):
    mocker.patch("time.sleep")
    _add_no_results(
        pesquisa=PESQUISA,
        pagina=1,
        tamanho_pagina=250,
        data_julgamento_inicio="01012024",
        data_julgamento_fim="31122024",
    )

    with pytest.warns(DeprecationWarning):
        stf.listar_decisoes(PESQUISA, paginas=1, data_inicio="01/01/2024", data_fim="31/12/2024")


@responses.activate
def test_alias_termo_vira_pesquisa(stf, mocker):
    mocker.patch("time.sleep")
    _add_no_results(pesquisa=PESQUISA, pagina=1, tamanho_pagina=250)

    with pytest.warns(DeprecationWarning):
        stf.listar_decisoes(termo=PESQUISA, paginas=1)


@pytest.mark.parametrize(
    "aliases,campo",
    [
        ({"data_julgamento_de": "01/01/2024", "data_julgamento_ate": "31/12/2024"}, "julgamento"),
        ({"data_publicacao_de": "01/01/2024", "data_publicacao_ate": "31/12/2024"}, "publicacao"),
    ],
)
@responses.activate
def test_aliases_de_ate_viram_datas_canonicas(stf, mocker, aliases, campo):
    mocker.patch("time.sleep")
    _add_no_results(
        pesquisa=PESQUISA,
        pagina=1,
        tamanho_pagina=250,
        **{f"data_{campo}_inicio": "01012024", f"data_{campo}_fim": "31122024"},
    )

    with pytest.warns(DeprecationWarning):
        stf.listar_decisoes(PESQUISA, paginas=1, **aliases)


def test_kwarg_desconhecido_levanta_type_error(stf):
    with pytest.raises(TypeError, match="ministro"):
        stf.listar_decisoes(PESQUISA, ministro="GILMAR MENDES")


def test_build_payload_aplica_filtros_como_o_portal():
    body = build_payload(
        "terceiriz$ ou pejotização",
        pagina=3,
        tamanho_pagina=50,
        base="acordaos",
        classe="Rcl",
        inteiro_teor=True,
        data_publicacao_fim="20082023",
    )
    consulta = body["query"]["function_score"]["query"]["bool"]

    assert consulta["filter"][0]["query_string"]["query"] == "terceiriz* OR pejotização"
    assert all(c["query_string"]["query"] == "terceiriz* OR pejotização" for c in consulta["should"])
    assert "inteiro_teor_texto.plural" in consulta["filter"][0]["query_string"]["fields"]
    assert "inteiro_teor_texto.plural^0.5" in consulta["should"][1]["query_string"]["fields"]
    assert consulta["filter"][1] == {"range": {"publicacao_data": {"format": "ddMMyyyy", "lte": "20082023"}}}
    filtro_classe = {"terms": {"processo_classe_processual_unificada_classe_sigla.keyword": ["Rcl"]}}
    assert body["post_filter"]["bool"]["must"] == [{"term": {"base": "acordaos"}}, filtro_classe]
    assert filtro_classe in body["aggs"]["ministro_facet_agg"]["filter"]["bool"]["must"]
    agg_classe = body["aggs"]["processo_classe_processual_unificada_classe_sigla_agg"]
    assert filtro_classe not in agg_classe["filter"]["bool"]["must"]
    assert (body["from"], body["size"]) == (100, 50)


def test_build_payload_sem_pesquisa_busca_tudo_e_encurta_ultima_pagina():
    body = build_payload(pagina=1429, tamanho_pagina=7)
    assert body["query"]["function_score"]["query"]["bool"]["filter"][0]["query_string"]["query"] == "*"
    assert (body["from"], body["size"]) == (9996, 4)


@pytest.mark.parametrize("base", ["decisoes", "acordaos"])
def test_build_payload_desempata_score_por_id_sem_mutar_o_template(base):
    build_payload(base=base)
    assert build_payload(base=base)["sort"] == [{"_score": "desc"}, {"id": "asc"}]


@pytest.mark.parametrize(
    "digitado,enviado",
    [
        # Pares observados no corpo que o portal envia para a API.
        ("direito e privacidade", "direito AND privacidade"),
        ("prisão não preventiva", "prisão NOT preventiva"),
        ("$constitucional", "*constitucional"),
        ("RE 56394?", "RE 56394?"),
        ("direito E (privacidade OU intimidade)", "direito AND (privacidade OR intimidade)"),
        ("terceirização ou terceiriz$", "terceirização OR terceiriz*"),
        # Operador so vale como palavra solta e fora de aspas.
        ("ouvidoria ou contrato", "ouvidoria OR contrato"),
        ('presunção de "não" culpabilidade', 'presunção de "não" culpabilidade'),
        ('"direito e dever$" ou multa', '"direito e dever$" OR multa'),
    ],
)
def test_traduzir_operadores_como_o_portal(digitado, enviado):
    assert traduzir_operadores(digitado) == enviado
