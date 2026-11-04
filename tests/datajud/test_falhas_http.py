"""Falhas HTTP da busca do DataJud: nova tentativa em 429 e causa real no erro.

Em 04/11/2026 o DataJud devolveu HTTP 429 com ``es_rejected_execution_exception``
(fila de busca do cluster cheia) a consultas que passavam inteiras uma hora
antes. Estes testes fixam o contrato da busca: 429, 502 e 503 são repetidos
com espera pelo perfil ``"busca"``, e a falha que sobra chega ao
``ColetaParcialError`` como a exceção original, com o status HTTP.
"""
from __future__ import annotations

import functools
import json
import logging
from typing import Any

import pytest
import requests
import responses

from juscraper.aggregators.datajud.client import DatajudScraper
from juscraper.aggregators.datajud.download import call_datajud_api
from juscraper.core import http as core_http
from juscraper.core.exceptions import ColetaParcialError, RetryExhaustedError

URL_TJAC = f"{DatajudScraper.BASE_API_URL}/api_publica_tjac/_search"
CORPO_429 = {
    "error": {
        "root_cause": [{"type": "es_rejected_execution_exception", "reason": "rejected execution"}],
        "type": "search_phase_execution_exception",
    },
    "status": 429,
}


def _pagina(pagina: int, *, tamanho: int = 10, total: int = 15) -> dict[str, Any]:
    hits = [
        {"_source": {"numeroProcesso": f"{pagina:02d}-{item:02d}"}, "sort": [f"cursor-{pagina:02d}-{item:02d}"]}
        for item in range(tamanho)
    ]
    return {"hits": {"total": {"value": total, "relation": "eq"}, "hits": hits}}


@pytest.fixture
def esperas(monkeypatch) -> list[float]:
    """Registra as esperas do retry do core, sem dormir.

    ``core.http`` e o client usam o mesmo módulo ``time``; os testes criam o
    scraper com ``sleep_time=0.0``, e a pausa nula entre páginas fica de fora.
    """
    registradas: list[float] = []

    def dormir(segundos: float) -> None:
        if segundos:
            registradas.append(segundos)

    monkeypatch.setattr(core_http.time, "sleep", dormir)
    return registradas


def _scraper() -> DatajudScraper:
    return DatajudScraper(verbose=0, sleep_time=0.0)


def _requisitar(**politica: Any):
    scraper = DatajudScraper(verbose=0, politica={"busca": politica} if politica else None)
    return functools.partial(scraper._request_with_retry, perfil="busca")  # noqa: SLF001


def _buscar(payload: dict[str, Any] | None = None, **politica: Any) -> dict[str, Any]:
    return call_datajud_api(
        base_url=DatajudScraper.BASE_API_URL,
        alias="api_publica_tjac",
        api_key="dummy",
        requisitar=_requisitar(**politica),
        query_payload=payload if payload is not None else {"query": {"match_all": {}}, "size": 100},
    )


# ---------------------------------------------------------------------------
# call_datajud_api
# ---------------------------------------------------------------------------


@responses.activate
@pytest.mark.parametrize("status", [429, 502, 503])
def test_status_repetivel_e_refeito_com_backoff(esperas, status):
    responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=status)
    responses.add(responses.POST, URL_TJAC, json=_pagina(1), status=200)

    assert _buscar() == _pagina(1)
    assert len(responses.calls) == 2
    assert esperas == [2.0]


@responses.activate
def test_429_respeita_retry_after_numerico(esperas):
    responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=429, headers={"Retry-After": "7"})
    responses.add(responses.POST, URL_TJAC, json=_pagina(1), status=200)

    _buscar()

    assert esperas == [7.0]


@responses.activate
def test_429_em_todas_as_tentativas_levanta_retry_esgotado(esperas):
    for _ in range(3):
        responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=429)

    with pytest.raises(RetryExhaustedError) as exc_info:
        _buscar()

    assert (exc_info.value.status_code, exc_info.value.attempts) == (429, 3)
    assert len(responses.calls) == 3
    assert esperas == [2.0, 4.0]


@responses.activate
def test_tentativas_e_backoff_vem_da_politica(esperas):
    for _ in range(5):
        responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=429)

    with pytest.raises(RetryExhaustedError):
        _buscar(max_retries=5, base_backoff=3.0)

    assert len(responses.calls) == 5
    assert esperas == [3.0, 9.0, 27.0, 81.0]


@responses.activate
@pytest.mark.parametrize("status", [400, 401, 403, 404, 500])
def test_status_nao_repetivel_levanta_httperror_com_a_resposta(esperas, status):
    responses.add(responses.POST, URL_TJAC, json={"error": "x"}, status=status)

    with pytest.raises(requests.HTTPError) as exc_info:
        _buscar()

    assert exc_info.value.response.status_code == status
    assert len(responses.calls) == 1
    assert esperas == []


@responses.activate
@pytest.mark.usefixtures("esperas")
def test_fallback_de_504_tambem_repete_429():
    """O 504 reduz o ``size``; a nova busca, se cair em 429, passa pelo retry do perfil."""
    responses.add(responses.POST, URL_TJAC, status=504)
    responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=429)
    responses.add(responses.POST, URL_TJAC, json=_pagina(1), status=200)
    payload = {"query": {"match_all": {}}, "size": 400}

    with pytest.warns(UserWarning, match="Refazendo com ``size=100``"):
        assert _buscar(payload) == _pagina(1)

    assert [json.loads(chamada.request.body)["size"] for chamada in responses.calls] == [400, 100, 100]


@responses.activate
@pytest.mark.usefixtures("esperas")
def test_erro_de_conexao_sobe():
    responses.add(responses.POST, URL_TJAC, body=requests.ConnectionError("recusada"))

    with pytest.raises(requests.ConnectionError, match="recusada"):
        _buscar()


@responses.activate
@pytest.mark.usefixtures("esperas")
def test_corpo_que_nao_e_json_sobe_como_erro_do_requests():
    responses.add(responses.POST, URL_TJAC, body="<html>manutenção</html>", status=200)

    with pytest.raises(requests.JSONDecodeError):
        _buscar()


@responses.activate
@pytest.mark.usefixtures("esperas")
def test_verbose_registra_url_e_status_sem_a_chave(caplog):
    responses.add(responses.POST, URL_TJAC, json=_pagina(1), status=200)

    with caplog.at_level(logging.DEBUG, logger="juscraper.aggregators.datajud.download"):
        call_datajud_api(
            base_url=DatajudScraper.BASE_API_URL,
            alias="api_publica_tjac",
            api_key="segredo",
            requisitar=_requisitar(),
            query_payload={"size": 10},
            verbose=True,
        )

    assert URL_TJAC in caplog.text
    assert "Response Status Code: 200" in caplog.text
    assert "segredo" not in caplog.text


# ---------------------------------------------------------------------------
# listar_processos e contar_processos
# ---------------------------------------------------------------------------


@responses.activate
def test_429_passageiro_nao_interrompe_a_coleta(esperas):
    responses.add(responses.POST, URL_TJAC, json=_pagina(1), status=200)
    responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=429)
    responses.add(responses.POST, URL_TJAC, json=_pagina(2, tamanho=5), status=200)

    df = _scraper().listar_processos(tribunal="TJAC", tamanho_pagina=10)

    assert len(df) == 15
    assert esperas == [2.0]


@responses.activate
@pytest.mark.usefixtures("esperas")
def test_429_esgotado_chega_ao_erro_parcial_como_causa():
    responses.add(responses.POST, URL_TJAC, json=_pagina(1), status=200)
    for _ in range(3):
        responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=429)

    with pytest.raises(ColetaParcialError) as exc_info:
        _scraper().listar_processos(tribunal="TJAC", tamanho_pagina=10)

    erro = exc_info.value
    causa = erro.falhas[0][2]
    assert isinstance(causa, RetryExhaustedError)
    assert causa.status_code == 429
    assert erro.__cause__ is causa
    assert "página 2" in str(erro)
    assert "Causa: HTTP 429 em todas as 3 tentativas." in str(erro)
    assert len(erro.resultado) == 10


@responses.activate
@pytest.mark.usefixtures("esperas")
def test_status_nao_repetivel_chega_ao_erro_parcial_com_a_resposta():
    responses.add(responses.POST, URL_TJAC, json={"error": "chave inválida"}, status=401)

    with pytest.raises(ColetaParcialError) as exc_info:
        _scraper().listar_processos(tribunal="TJAC")

    erro = exc_info.value
    causa = erro.falhas[0][2]
    assert isinstance(causa, requests.HTTPError)
    assert causa.response.status_code == 401
    assert erro.__cause__ is causa
    assert "Causa: HTTP 401." in str(erro)


@responses.activate
@pytest.mark.usefixtures("esperas")
def test_timeout_chega_ao_erro_parcial_como_causa():
    responses.add(responses.POST, URL_TJAC, body=requests.ReadTimeout("lento"))

    with pytest.raises(ColetaParcialError) as exc_info:
        _scraper().listar_processos(tribunal="TJAC", tamanho_pagina=100)

    assert isinstance(exc_info.value.__cause__, requests.ReadTimeout)
    assert "Causa: timeout." in str(exc_info.value)


@responses.activate
def test_contar_processos_repete_429_passageiro(esperas):
    responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=429)
    responses.add(responses.POST, URL_TJAC, json=_pagina(1, tamanho=0), status=200)

    linha = _scraper().contar_processos(tribunal="TJAC").iloc[0]

    assert (linha["count"], linha["error"]) == (15, None)
    assert esperas == [2.0]


@responses.activate
@pytest.mark.usefixtures("esperas")
def test_contar_processos_informa_o_status_que_sobra():
    for _ in range(3):
        responses.add(responses.POST, URL_TJAC, json=CORPO_429, status=429)

    linha = _scraper().contar_processos(tribunal="TJAC").iloc[0]

    assert linha["count"] is None
    assert linha["error"] == "HTTP 429 em todas as 3 tentativas"
