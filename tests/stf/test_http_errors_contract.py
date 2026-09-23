"""Falhas HTTP e respostas parciais da busca do STF."""
import json

import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import RetryExhaustedError
from juscraper.courts.stf.download import BASE_URL
from tests._helpers import load_sample


@pytest.mark.parametrize(
    "resposta",
    [
        {"json": {"message": "Forbidden"}},
        {"body": "<html>Request blocked</html>", "content_type": "text/html"},
    ],
    ids=["json-sem-detail", "corpo-nao-json"],
)
@responses.activate
def test_403_sem_detail_e_retentado_ate_esgotar(mocker, resposta):
    mocker.patch("time.sleep")
    responses.add(responses.POST, BASE_URL, status=403, **resposta)

    with pytest.raises(RetryExhaustedError):
        jus.scraper("stf", waf_token="token-de-teste").listar_decisoes("pejotização", paginas=1)

    assert len(responses.calls) == 3


@pytest.mark.parametrize("endpoint", ["listar_decisoes", "contar_decisoes"])
@pytest.mark.parametrize("failure", ["timeout", "failed_shard"])
@responses.activate
def test_partial_search_response_is_rejected(mocker, endpoint, failure):
    mocker.patch("time.sleep")
    payload = json.loads(load_sample("stf", "listar_decisoes/no_results.json"))
    # Falhas sintéticas sobre o formato capturado, sem alterar o sample real.
    if failure == "timeout":
        payload["result"]["timed_out"] = True
    else:
        payload["result"]["_shards"].update(total=2, successful=1, skipped=0, failed=1)
    responses.add(responses.POST, BASE_URL, status=200, json=payload)
    stf = jus.scraper("stf", waf_token="token-de-teste")

    with pytest.raises(RuntimeError, match="resposta incompleta"):
        getattr(stf, endpoint)("pejotização")
    assert len(responses.calls) == 1


@pytest.mark.parametrize("paginas", [None, 3])
@responses.activate
def test_partial_later_page_aborts_the_whole_collection(mocker, paginas):
    mocker.patch("time.sleep")
    first = json.loads(load_sample("stf", "listar_decisoes/results_normal_page_01.json"))
    first["result"]["hits"]["total"]["value"] = 15
    partial = json.loads(load_sample("stf", "listar_decisoes/results_normal_page_02.json"))
    partial["result"]["timed_out"] = True
    responses.add(responses.POST, BASE_URL, json=first)
    responses.add(responses.POST, BASE_URL, json=partial)
    stf = jus.scraper("stf", waf_token="token-de-teste")

    with pytest.raises(RuntimeError, match="resposta incompleta"):
        stf.listar_decisoes("pejotização", paginas=paginas, tamanho_pagina=5)

    assert len(responses.calls) == 2
