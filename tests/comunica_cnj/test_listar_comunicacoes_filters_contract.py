"""Filters propagation for ``ComunicaCNJScraper.listar_comunicacoes``.

Confirma que cada filtro aceito pelo schema chega como parametro de
querystring no GET ao endpoint, no nome canonico esperado pela API
(``texto``, ``itensPorPagina``, ``pagina``, ``dataDisponibilizacaoInicio``,
``dataDisponibilizacaoFim``). Cobre tambem:

- conversao automatica de datas em ``DD/MM/YYYY`` para ISO ``YYYY-MM-DD``
  via ``to_iso_date`` (regra 4 do CLAUDE.md "Convencao de API");
- validacao de intervalo de datas (``inicio > fim``) via
  ``validate_intervalo_datas`` antes de qualquer requisicao;
- ausencia de aliases deprecados (a API ComunicaCNJ e nova; o schema
  usa ``data_disponibilizacao_inicio``/``_fim`` como nomes canonicos
  exatamente para evitar colisao com ``data_inicio``/``data_fim``, que
  no resto do projeto sao aliases deprecados de ``data_julgamento_*``).
"""
from __future__ import annotations

import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.aggregators.comunica_cnj.download import BASE_URL, build_listar_comunicacoes_params
from tests._helpers import load_sample


@responses.activate
def test_listar_comunicacoes_all_filters_land_in_querystring(mocker):
    """Todos os filtros chegam simultaneamente: ``texto``, ``pagina``,
    ``itensPorPagina``, ``dataDisponibilizacaoInicio`` e
    ``dataDisponibilizacaoFim``."""
    mocker.patch("time.sleep")
    params = build_listar_comunicacoes_params(
        pesquisa="resolucao",
        pagina=1,
        itens_por_pagina=50,
        data_disponibilizacao_inicio="2024-01-01",
        data_disponibilizacao_fim="2024-01-31",
    )
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("comunica_cnj", "listar_comunicacoes/single_page.json"),
        status=200,
        content_type="application/json",
        match=[query_param_matcher({k: str(v) for k, v in params.items()})],
    )

    df = jus.scraper("comunica_cnj").listar_comunicacoes(
        pesquisa="resolucao",
        itens_por_pagina=50,
        data_disponibilizacao_inicio="2024-01-01",
        data_disponibilizacao_fim="2024-01-31",
    )

    assert isinstance(df, pd.DataFrame)
    # A asserva fundamental e o matcher acima — se nao bater, o
    # ``responses`` levanta ``ConnectionError`` antes de chegar aqui.


@responses.activate
def test_listar_comunicacoes_aceita_data_em_formato_brasileiro(mocker):
    """Datas em ``DD/MM/YYYY`` sao convertidas para ISO antes do GET.
    Cobre a integracao do ``to_iso_date`` com o schema."""
    mocker.patch("time.sleep")
    params = build_listar_comunicacoes_params(
        pesquisa="resolucao",
        pagina=1,
        itens_por_pagina=100,
        data_disponibilizacao_inicio="2024-01-01",
        data_disponibilizacao_fim="2024-01-31",
    )
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("comunica_cnj", "listar_comunicacoes/single_page.json"),
        status=200,
        content_type="application/json",
        match=[query_param_matcher({k: str(v) for k, v in params.items()})],
    )

    df = jus.scraper("comunica_cnj").listar_comunicacoes(
        pesquisa="resolucao",
        data_disponibilizacao_inicio="01/01/2024",
        data_disponibilizacao_fim="31/01/2024",
    )

    assert isinstance(df, pd.DataFrame)


def test_listar_comunicacoes_intervalo_invertido_levanta_valueerror():
    """``data_disponibilizacao_inicio > data_disponibilizacao_fim``
    levanta ``ValueError`` via ``validate_intervalo_datas`` antes de
    qualquer requisicao HTTP."""
    with pytest.raises(ValueError):
        jus.scraper("comunica_cnj").listar_comunicacoes(
            pesquisa="resolucao",
            data_disponibilizacao_inicio="2024-12-31",
            data_disponibilizacao_fim="2024-01-01",
        )


def test_listar_comunicacoes_data_inicio_e_alias_desconhecido():
    """``data_inicio`` (sem prefixo) e alias deprecado em outros
    scrapers para ``data_julgamento_inicio``. Aqui nao e aceito — o
    nome canonico do schema e ``data_disponibilizacao_inicio``. Garante
    que o schema rejeita o alias generico, evitando o caso ambiguo
    onde o usuario passaria ``data_inicio`` esperando filtro de
    disponibilizacao mas o normalizador o trataria como julgamento."""
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        jus.scraper("comunica_cnj").listar_comunicacoes(
            pesquisa="resolucao",
            data_inicio="2024-01-01",
        )


def test_listar_comunicacoes_itens_por_pagina_acima_do_cap():
    """``itens_por_pagina`` acima de 100 (limite documentado da API)
    e rejeitado pelo schema antes da requisicao."""
    with pytest.raises(ValidationError):
        jus.scraper("comunica_cnj").listar_comunicacoes(
            pesquisa="resolucao",
            itens_por_pagina=500,
        )


def test_listar_comunicacoes_itens_por_pagina_zero():
    """``itens_por_pagina < 1`` e rejeitado pelo schema (``ge=1``)."""
    with pytest.raises(ValidationError):
        jus.scraper("comunica_cnj").listar_comunicacoes(
            pesquisa="resolucao",
            itens_por_pagina=0,
        )
