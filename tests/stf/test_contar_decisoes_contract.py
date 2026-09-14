"""Offline contract tests for STF contar_decisoes."""
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.stf.download import BASE_URL, build_payload
from tests._helpers import load_sample


@responses.activate
def test_contar_decisoes_total_e_facetas():
    """Um POST com ``size=0``; a primeira linha e o total e as demais sao buckets das facetas."""
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("stf", "contar_decisoes/results_normal.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_payload("pejotização", classe="Rcl", tamanho_pagina=0))],
    )

    df = jus.scraper("stf", waf_token="token-de-teste").contar_decisoes("pejotização", classe="Rcl")

    assert list(df.columns) == ["faceta", "valor", "n"]
    assert df.iloc[0].to_dict() == {"faceta": "total", "valor": None, "n": 3369}
    facetas = set(df["faceta"])
    assert {"base", "ministro_facet", "processo_classe_processual_unificada_classe_sigla"} <= facetas
    decisoes = df[(df["faceta"] == "base") & (df["valor"] == "decisoes")]["n"].item()
    assert decisoes >= 3369
