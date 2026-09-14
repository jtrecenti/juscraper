"""Filter propagation, empty result and aliases for STF contar_decisoes."""
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.stf.download import BASE_URL, build_payload
from tests._helpers import load_sample

PESQUISA = "juscraper_probe_zero_hits_xyzqwe"


def _add_no_results(pesquisa, **payload_kwargs) -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("stf", "listar_decisoes/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_payload(pesquisa, tamanho_pagina=0, **payload_kwargs))],
    )


@pytest.fixture
def stf():
    return jus.scraper("stf", waf_token="token-de-teste")


@responses.activate
def test_todos_os_filtros_chegam_ao_corpo_e_busca_vazia_da_total_zero(stf):
    _add_no_results(
        PESQUISA,
        base="acordaos",
        classe=["Rcl", "ARE"],
        inteiro_teor=True,
        data_julgamento_inicio="01012024",
        data_julgamento_fim="31122024",
        data_publicacao_inicio="01022024",
        data_publicacao_fim="30112024",
    )

    df = stf.contar_decisoes(
        PESQUISA,
        base="acordaos",
        classe=["Rcl", "ARE"],
        inteiro_teor=True,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="30/11/2024",
    )

    assert len(responses.calls) == 1
    assert df.iloc[0].to_dict() == {"faceta": "total", "valor": None, "n": 0}


@responses.activate
def test_sem_termo_conta_tudo_com_curinga(stf):
    _add_no_results("*", classe="Rcl")

    stf.contar_decisoes(classe="Rcl")

    assert len(responses.calls) == 1


@responses.activate
def test_alias_termo_vira_pesquisa(stf):
    _add_no_results(PESQUISA)

    with pytest.warns(DeprecationWarning):
        stf.contar_decisoes(termo=PESQUISA)


def test_tamanho_pagina_nao_e_filtro_de_contagem(stf):
    with pytest.raises(TypeError, match="tamanho_pagina"):
        stf.contar_decisoes(PESQUISA, tamanho_pagina=10)
