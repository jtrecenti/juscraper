"""Offline contract tests for STF listar_decisoes."""
import json

import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.stf.download import BASE_URL, build_payload
from tests._helpers import load_sample

MIN_COLUMNS = {
    "processo",
    "classe",
    "relator",
    "data_julgamento",
    "data_publicacao",
    "decisao_texto",
    "inteiro_teor_url",
}


def _add(sample: str, **payload_kwargs) -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("stf", f"listar_decisoes/{sample}"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_payload(**payload_kwargs))],
    )


@pytest.fixture
def stf():
    return jus.scraper("stf", waf_token="token-de-teste")


@responses.activate
def test_listar_decisoes_com_paginacao(stf, mocker):
    """Duas paginas pedidas viram dois POSTs e um DataFrame com as colunas canonicas."""
    mocker.patch("time.sleep")
    _add("results_normal_page_01.json", pesquisa="pejotização", classe="Rcl", pagina=1, tamanho_pagina=5)
    _add("results_normal_page_02.json", pesquisa="pejotização", classe="Rcl", pagina=2, tamanho_pagina=5)

    df = stf.listar_decisoes("pejotização", classe="Rcl", paginas=range(1, 3), tamanho_pagina=5)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= MIN_COLUMNS
    assert len(df) == 10
    assert set(df["classe"]) == {"Rcl"}
    assert responses.calls[0].request.headers["Cookie"] == "aws-waf-token=token-de-teste"


@responses.activate
def test_listar_decisoes_todas_as_paginas_com_datas(stf, mocker):
    """``paginas=None`` para depois da primeira pagina quando o total cabe nela; datas saem em ddMMyyyy."""
    mocker.patch("time.sleep")
    _add(
        "single_page.json",
        pesquisa="pejotização",
        pagina=1,
        tamanho_pagina=250,
        data_julgamento_inicio="01012020",
        data_julgamento_fim="31122020",
    )

    df = stf.listar_decisoes(
        "pejotização", data_julgamento_inicio="01/01/2020", data_julgamento_fim="2020-12-31"
    )

    assert len(responses.calls) == 1
    assert set(df.columns) >= MIN_COLUMNS
    assert len(df) == 2


@responses.activate
def test_listar_decisoes_sem_resultados(stf, mocker):
    """Busca sem resultados devolve DataFrame vazio."""
    mocker.patch("time.sleep")
    _add("no_results.json", pesquisa="juscraper_probe_zero_hits_xyzqwe", pagina=1, tamanho_pagina=250)

    df = stf.listar_decisoes("juscraper_probe_zero_hits_xyzqwe")

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_pagina_alem_do_teto_falha_sem_requisicao(stf):
    """A pagina que comeca depois do registro 10.000 e recusada antes de qualquer POST."""
    with pytest.raises(ValueError, match="10000 primeiros registros"):
        stf.listar_decisoes("terceiriz$", paginas=[1, 41], tamanho_pagina=250)
    assert len(responses.calls) == 0


@responses.activate
def test_limite_da_api_vira_value_error_sem_retry(stf, mocker):
    """O 403 com ``detail`` e regra da API: sobe ``ValueError`` na primeira resposta."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        json={"detail": "Excedido o limite de 250 documentos por consulta."},
        status=403,
    )

    with pytest.raises(ValueError, match="limite de 250"):
        stf.listar_decisoes("pejotização", paginas=1)
    assert len(responses.calls) == 1


@responses.activate
def test_desafio_do_waf_renova_o_token_e_repete(stf, mocker):
    """HTTP 202 com challenge renova o cookie uma vez e repete a mesma busca."""
    mocker.patch("time.sleep")
    obter = mocker.patch("juscraper.courts.stf.client.obter_waf_token", return_value="token-novo")
    responses.add(responses.POST, BASE_URL, body="", status=202, headers={"x-amzn-waf-action": "challenge"})
    _add("no_results.json", pesquisa="juscraper_probe_zero_hits_xyzqwe", pagina=1, tamanho_pagina=250)

    df = stf.listar_decisoes("juscraper_probe_zero_hits_xyzqwe")

    assert df.empty
    obter.assert_called_once_with()
    assert responses.calls[1].request.headers["Cookie"] == "aws-waf-token=token-novo"


@responses.activate
def test_desafio_repetido_depois_da_renovacao_levanta(stf, mocker):
    """Se o WAF desafiar de novo com o cookie recem-obtido, o scraper para."""
    mocker.patch("time.sleep")
    mocker.patch("juscraper.courts.stf.client.obter_waf_token", return_value="token-novo")
    responses.add(responses.POST, BASE_URL, body="", status=202, headers={"x-amzn-waf-action": "challenge"})

    with pytest.raises(RuntimeError, match="desafiou de novo"):
        stf.listar_decisoes("pejotização", paginas=1)
    assert len(responses.calls) == 2


@responses.activate
def test_sem_token_obtem_um_antes_da_primeira_busca(mocker):
    """Sem ``waf_token``, o cookie e obtido antes do primeiro POST."""
    mocker.patch("time.sleep")
    obter = mocker.patch("juscraper.courts.stf.client.obter_waf_token", return_value="token-obtido")
    _add("no_results.json", pesquisa="juscraper_probe_zero_hits_xyzqwe", pagina=1, tamanho_pagina=250)

    jus.scraper("stf").listar_decisoes("juscraper_probe_zero_hits_xyzqwe")

    obter.assert_called_once_with()
    assert responses.calls[0].request.headers["Cookie"] == "aws-waf-token=token-obtido"


@responses.activate
def test_paginas_none_busca_as_paginas_seguintes(stf, mocker):
    """Sem ``paginas``, o total da primeira resposta define quantas paginas faltam."""
    mocker.patch("time.sleep")
    pagina_1 = json.loads(load_sample("stf", "listar_decisoes/results_normal_page_01.json"))
    # O sample real tem 3.369 resultados; com total 10 e 5 por pagina, falta uma pagina.
    pagina_1["result"]["hits"]["total"]["value"] = 10
    responses.add(
        responses.POST,
        BASE_URL,
        json=pagina_1,
        match=[json_params_matcher(build_payload("pejotização", classe="Rcl", pagina=1, tamanho_pagina=5))],
    )
    _add("results_normal_page_02.json", pesquisa="pejotização", classe="Rcl", pagina=2, tamanho_pagina=5)

    df = stf.listar_decisoes("pejotização", classe="Rcl", tamanho_pagina=5)

    assert len(responses.calls) == 2
    assert len(df) == 10


@responses.activate
def test_paginas_none_para_no_teto_com_aviso(stf, mocker):
    """Com mais de 10.000 resultados, baixa 40 paginas de 250, a ultima terminando no registro 10.000."""
    mocker.patch("time.sleep")
    pagina = json.loads(load_sample("stf", "listar_decisoes/results_normal_page_01.json"))
    pagina["result"]["hits"]["total"]["value"] = 16899
    responses.add(responses.POST, BASE_URL, json=pagina)

    with pytest.warns(UserWarning, match="so entrega os 10000"):
        stf.listar_decisoes("terceirização", tamanho_pagina=250)

    assert len(responses.calls) == 40
    ultimo = json.loads(responses.calls[-1].request.body)
    assert (ultimo["from"], ultimo["size"]) == (9750, 250)
