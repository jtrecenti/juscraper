"""Offline contract for ``ComunicaCNJScraper.listar_comunicacoes``.

Cada teste mocka o endpoint REST GET em
``https://comunicaapi.pje.jus.br/api/v1/comunicacao`` via
:mod:`responses` e valida tanto a querystring enviada (via
``query_param_matcher``) quanto o shape do DataFrame produzido. Os
samples vivem em ``tests/comunica_cnj/samples/listar_comunicacoes/`` e
sao gerados por ``python -m tests.fixtures.capture.comunica_cnj`` contra
a API real do CNJ.

A funcao ``build_listar_comunicacoes_params`` importada do modulo
``download`` e a unica fonte da verdade da querystring — capture, client
e contrato compartilham o mesmo builder, evitando drift silencioso
(regra 12 do CLAUDE.md).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import query_param_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.aggregators.comunica_cnj.download import BASE_URL, build_listar_comunicacoes_params
from tests._helpers import assert_unknown_kwarg_raises, load_sample

LISTAR_COMUNICACOES_MIN_COLUMNS = {
    "numero_processo",
    "siglaTribunal",
    "texto",
    "link",
    "data_disponibilizacao",
}


def _add_page(sample_path: str, **builder_kwargs) -> None:
    """Mocka uma chamada GET ao endpoint com os parametros gerados pelo builder."""
    params = build_listar_comunicacoes_params(**builder_kwargs)
    # ``responses.matchers.query_param_matcher`` espera strings — a API
    # recebe ints serializados como strings na URL.
    params_str = {k: str(v) for k, v in params.items()}
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("comunica_cnj", sample_path),
        status=200,
        content_type="application/json",
        match=[query_param_matcher(params_str)],
    )


@responses.activate(registry=OrderedRegistry)
def test_listar_comunicacoes_typical_multi_page(mocker):
    """Duas requisicoes: page 1 e page 2 da mesma busca paginada."""
    mocker.patch("time.sleep")
    _add_page(
        "listar_comunicacoes/results_normal_page_01.json",
        pesquisa="resolucao",
        pagina=1,
        itens_por_pagina=10,
    )
    _add_page(
        "listar_comunicacoes/results_normal_page_02.json",
        pesquisa="resolucao",
        pagina=2,
        itens_por_pagina=10,
    )

    df = jus.scraper("comunica_cnj").listar_comunicacoes(
        pesquisa="resolucao",
        paginas=range(1, 3),
        itens_por_pagina=10,
    )

    assert isinstance(df, pd.DataFrame)
    assert LISTAR_COMUNICACOES_MIN_COLUMNS <= set(df.columns)
    assert len(df) == 20


@responses.activate
def test_listar_comunicacoes_single_page(mocker):
    """``count <= itens_por_pagina`` -- so uma pagina e baixada."""
    mocker.patch("time.sleep")
    _add_page(
        "listar_comunicacoes/single_page.json",
        pesquisa="embargos infringentes",
        pagina=1,
        itens_por_pagina=100,
        data_disponibilizacao_inicio="2024-06-03",
        data_disponibilizacao_fim="2024-06-03",
    )

    df = jus.scraper("comunica_cnj").listar_comunicacoes(
        pesquisa="embargos infringentes",
        data_disponibilizacao_inicio="2024-06-03",
        data_disponibilizacao_fim="2024-06-03",
    )

    assert isinstance(df, pd.DataFrame)
    assert LISTAR_COMUNICACOES_MIN_COLUMNS <= set(df.columns)
    sample = json.loads(
        load_sample("comunica_cnj", "listar_comunicacoes/single_page.json")
    )
    assert len(df) == sample["count"]


@responses.activate
def test_listar_comunicacoes_no_results(mocker):
    """``items == []`` retorna DataFrame vazio, nao erro."""
    mocker.patch("time.sleep")
    _add_page(
        "listar_comunicacoes/no_results.json",
        pesquisa="juscraper_probe_zero_hits_xyzqwe",
        pagina=1,
        itens_por_pagina=100,
    )

    df = jus.scraper("comunica_cnj").listar_comunicacoes(
        pesquisa="juscraper_probe_zero_hits_xyzqwe",
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_listar_comunicacoes_pesquisa_obrigatoria():
    """``pesquisa=None`` levanta ``ValidationError`` via pydantic
    (``pesquisa: str`` no schema, sem default)."""
    with pytest.raises(ValidationError):
        jus.scraper("comunica_cnj").listar_comunicacoes()


def test_listar_comunicacoes_unknown_kwarg_raises_typeerror():
    """``extra='forbid'`` no schema + ``raise_on_extra_kwargs`` traduz
    kwarg desconhecido em ``TypeError`` amigavel."""
    assert_unknown_kwarg_raises(
        jus.scraper("comunica_cnj").listar_comunicacoes,
        "parametro_inventado",
        pesquisa="resolucao",
    )


@responses.activate
def test_listar_comunicacoes_legacy_itens_key_fallback(mocker):
    """A versao anterior da API usava ``itens`` (PT) em vez de ``items``
    (EN). O parser deve aceitar ambos. Cobre o bugfix mencionado no PR
    body: refs ``bdcdo/raspe#14``."""
    mocker.patch("time.sleep")
    legacy_body = {
        "status": "success",
        "message": "OK",
        "count": 1,
        "itens": [
            {
                "numero_processo": "0000001-23.2024.8.26.0000",
                "siglaTribunal": "TJSP",
                "texto": "[truncado]",
                "link": "https://example.test/comunicacao/1",
                "data_disponibilizacao": "2024-01-15",
            }
        ],
    }
    params = build_listar_comunicacoes_params(
        pesquisa="legacy", pagina=1, itens_por_pagina=100
    )
    responses.add(
        responses.GET,
        BASE_URL,
        json=legacy_body,
        status=200,
        match=[query_param_matcher({k: str(v) for k, v in params.items()})],
    )

    df = jus.scraper("comunica_cnj").listar_comunicacoes(pesquisa="legacy")

    assert len(df) == 1
    assert df.iloc[0]["numero_processo"] == "0000001-23.2024.8.26.0000"
