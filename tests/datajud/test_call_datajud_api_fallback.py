"""Fallback automatico em ``HTTP 504``/``Timeout`` no ``call_datajud_api``.

Em condicoes reais a API publica do DataJud (gateway intermediario) corta
em ~60s qualquer requisicao que demore mais do que isso, retornando
``HTTP 504``. Como o tempo de resposta cresce com o ``size``, valores
proximos do cap (10000) estouram intermitentemente. O fallback automatico
refaz a requisicao 1 unica vez com ``size`` reduzido (default ``size // 4``,
minimo 100) antes de desistir, mutando ``query_payload`` em place para que o
caller (``_listar_processos_por_alias``) leia o size efetivo na heuristica
de "ultima pagina".

Estes testes mockam a chamada HTTP para validar o contrato do retry sem
depender da rede.
"""
from __future__ import annotations

import warnings

import pytest
import requests
import responses

from juscraper.aggregators.datajud.client import DatajudScraper
from juscraper.aggregators.datajud.download import FALLBACK_DIVISOR, FALLBACK_MIN_SIZE, call_datajud_api

BASE = DatajudScraper.BASE_API_URL
ALIAS = "api_publica_tjsp"
URL = f"{BASE}/{ALIAS}/_search"
SUCCESS_BODY = {"hits": {"total": {"value": 1, "relation": "eq"}, "hits": []}}


def _payload(size: int) -> dict:
    return {
        "query": {"match_all": {}},
        "size": size,
        "track_total_hits": True,
        "sort": [{"id.keyword": "asc"}],
        "_source": {"excludes": ["movimentacoes", "movimentos"]},
    }


@responses.activate
def test_fallback_em_504_refaz_com_size_reduzido():
    """``HTTP 504`` na 1a chamada -> retry com ``size // FALLBACK_DIVISOR``."""
    responses.add(responses.POST, URL, status=504)
    responses.add(responses.POST, URL, json=SUCCESS_BODY, status=200)

    payload = _payload(size=4000)
    expected_retry_size = max(4000 // FALLBACK_DIVISOR, FALLBACK_MIN_SIZE)

    with pytest.warns(UserWarning, match=r"504/timeout em ``size=4000``"):
        result = call_datajud_api(
            base_url=BASE,
            alias=ALIAS,
            api_key="dummy",
            session=requests.Session(),
            query_payload=payload,
        )

    assert result == SUCCESS_BODY
    assert len(responses.calls) == 2
    # O size do payload foi mutado em place — o caller le esse valor na
    # heuristica de ultima pagina (``len(hits) < query_payload['size']``).
    assert payload["size"] == expected_retry_size


@responses.activate
def test_fallback_em_timeout_refaz_com_size_reduzido():
    """``requests.Timeout`` na 1a chamada -> retry com ``size`` reduzido."""
    responses.add(responses.POST, URL, body=requests.exceptions.Timeout())
    responses.add(responses.POST, URL, json=SUCCESS_BODY, status=200)

    payload = _payload(size=5000)
    with pytest.warns(UserWarning, match="504/timeout"):
        result = call_datajud_api(
            base_url=BASE,
            alias=ALIAS,
            api_key="dummy",
            session=requests.Session(),
            query_payload=payload,
        )

    assert result == SUCCESS_BODY
    assert payload["size"] == max(5000 // FALLBACK_DIVISOR, FALLBACK_MIN_SIZE)


@responses.activate
def test_fallback_so_uma_vez_se_falhar_de_novo_retorna_none():
    """Se o retry tambem cair em 504, segue o fluxo normal: ``None``."""
    responses.add(responses.POST, URL, status=504)
    responses.add(responses.POST, URL, status=504)

    payload = _payload(size=5000)
    with pytest.warns(UserWarning, match="504/timeout"):
        result = call_datajud_api(
            base_url=BASE,
            alias=ALIAS,
            api_key="dummy",
            session=requests.Session(),
            query_payload=payload,
        )

    assert result is None
    assert len(responses.calls) == 2  # 1a tentativa + 1 retry, nao mais


@responses.activate
def test_sem_fallback_quando_size_ja_no_minimo():
    """Se ``size <= FALLBACK_MIN_SIZE``, nao faz retry — reduzir mais nao
    ajuda. Cai direto no fluxo normal de erro (``None``, sem ``UserWarning``)."""
    responses.add(responses.POST, URL, status=504)

    payload = _payload(size=FALLBACK_MIN_SIZE)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = call_datajud_api(
            base_url=BASE,
            alias=ALIAS,
            api_key="dummy",
            session=requests.Session(),
            query_payload=payload,
        )

    assert result is None
    assert len(responses.calls) == 1  # Sem retry
    assert payload["size"] == FALLBACK_MIN_SIZE  # Nao mutado
    assert not [w for w in caught if "504/timeout" in str(w.message)]


@responses.activate
def test_sem_fallback_em_outros_5xx():
    """``HTTP 500`` (erro genuino do servidor, nao gateway timeout) nao
    aciona fallback — reduzir o ``size`` nao corrige bug do servidor."""
    responses.add(responses.POST, URL, status=500)

    payload = _payload(size=5000)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = call_datajud_api(
            base_url=BASE,
            alias=ALIAS,
            api_key="dummy",
            session=requests.Session(),
            query_payload=payload,
        )

    assert result is None
    assert len(responses.calls) == 1
    assert payload["size"] == 5000  # Nao mutado
    assert not [w for w in caught if "504/timeout" in str(w.message)]
