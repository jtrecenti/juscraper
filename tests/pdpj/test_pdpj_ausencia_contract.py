"""Como o PDPJ diz "não há registro", e como o raspador lê cada forma.

Medido em campo, com token válido: a página seguinte à última da ``pesquisa``
vem como 404 com ``{code, message}``; o processo que não está no índice do
data lake responde 500 nos endpoints por processo (``/processos/{n}``,
``/documentos``, ``/movimentos``, ``/partes``) e 404 na ``pesquisa`` por
``numeroProcesso``; o processo inexistente responde 404 na listagem de
documentos. O 500 sozinho não distingue ausência de pane, por isso o raspador
só marca o processo como ausente com os dois sinais juntos.
"""
from __future__ import annotations

import json
import warnings

import pytest
import requests
import responses

import juscraper as jus
from juscraper.aggregators.pdpj.download import BASE_URL
from juscraper.core.exceptions import RetryExhaustedError
from juscraper.core.failures import MOTIVOS_FALHA
from tests._helpers import load_sample

FAKE_TOKEN = (
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
    "eyJzdWIiOiJ0ZXN0IiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDB9."
)
PROC = "10029886420194014100"
OUTRO = "00000011120248260100"
PESQUISA = f"{BASE_URL}/processos"
SEM_REGISTROS = json.dumps({"code": 404, "message": "Não foram encontrados registros"})

METODOS_DE_LISTA = {
    "cpopg": ("", "cpopg/processo_encontrado.json"),
    "documentos": ("/documentos", "documentos/lista_normal.json"),
    "movimentos": ("/movimentos", "movimentos/lista_normal.json"),
    "partes": ("/partes", "partes/lista_normal.json"),
}


def _mk_scraper():
    s = jus.scraper("pdpj", sleep_time=0)
    s.auth(FAKE_TOKEN)
    return s


def _mock(url: str, status: int = 200, body: str = "") -> None:
    responses.add(responses.GET, url, body=body, status=status, content_type="application/json")


def _chamadas(url: str) -> int:
    return sum(1 for call in responses.calls if call.request.url.split("?")[0] == url)


def _pagina_1() -> None:
    _mock(PESQUISA, body=load_sample("pdpj", "pesquisa/single_page.json"))


def test_nao_encontrado_esta_no_vocabulario():
    assert "nao_encontrado" in MOTIVOS_FALHA


# ---------------------------------------------------------------------
# página terminal da pesquisa
# ---------------------------------------------------------------------

@responses.activate
def test_pesquisa_404_depois_da_ultima_pagina_encerra_a_coleta():
    _pagina_1()
    _mock(PESQUISA, status=404, body=SEM_REGISTROS)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        df = _mk_scraper().pesquisa(tribunal="TRF1")

    assert len(df) == 1
    assert _chamadas(PESQUISA) == 2
    assert "searchAfter" in responses.calls[1].request.url


@responses.activate
def test_pesquisa_404_na_primeira_pagina_devolve_vazio():
    _mock(PESQUISA, status=404, body=SEM_REGISTROS)

    df = _mk_scraper().pesquisa(numero_processo=OUTRO)

    assert df.empty
    assert _chamadas(PESQUISA) == 1


@pytest.mark.parametrize(("status", "erro"), [(403, requests.HTTPError), (500, RetryExhaustedError)])
@responses.activate
def test_pesquisa_outro_status_na_pagina_2_continua_levantando(status, erro):
    _pagina_1()
    _mock(PESQUISA, status=status)

    with pytest.raises(erro):
        _mk_scraper().pesquisa(tribunal="TRF1")


@responses.activate
def test_pesquisa_401_na_pagina_2_propaga():
    _pagina_1()
    _mock(PESQUISA, status=401)

    with pytest.raises(requests.HTTPError) as erro:
        _mk_scraper().pesquisa(tribunal="TRF1")

    assert erro.value.response.status_code == 401


# Os 404 dos endpoints por processo estão em test_pdpj_failure_contract.py,
# ao lado dos demais motivos da linha de falha.


# ---------------------------------------------------------------------
# processo ausente: 500 confirmado pela pesquisa
# ---------------------------------------------------------------------

@pytest.mark.parametrize("metodo", list(METODOS_DE_LISTA))
@responses.activate
def test_500_com_pesquisa_404_para_na_primeira_tentativa(metodo, esperas_do_backoff):
    sufixo, _sample = METODOS_DE_LISTA[metodo]
    endpoint = f"{BASE_URL}/processos/{OUTRO}{sufixo}"
    _mock(endpoint, status=500)
    _mock(PESQUISA, status=404, body=SEM_REGISTROS)

    with pytest.warns(UserWarning, match=f"processo {OUTRO}: nao_encontrado"):
        df = getattr(_mk_scraper(), metodo)(OUTRO)

    assert _chamadas(endpoint) == 1
    assert _chamadas(PESQUISA) == 1
    assert f"numeroProcesso={OUTRO}" in responses.calls[1].request.url
    assert df["motivo_falha"].tolist() == ["nao_encontrado"]
    esperas_do_backoff.assert_not_called()


@responses.activate
def test_500_com_pesquisa_200_retenta_pelo_perfil():
    endpoint = f"{BASE_URL}/processos/{PROC}/documentos"
    _mock(endpoint, status=500)
    _pagina_1()

    with pytest.warns(UserWarning, match="retry_esgotado_500"):
        df = _mk_scraper().documentos(PROC)

    assert _chamadas(endpoint) == 6
    assert _chamadas(PESQUISA) == 1
    assert df["motivo_falha"].tolist() == ["retry_esgotado_500"]


@responses.activate
def test_500_passageiro_com_pesquisa_200_entrega_o_processo():
    endpoint = f"{BASE_URL}/processos/{PROC}/documentos"
    _mock(endpoint, status=500)
    _mock(endpoint, body=load_sample("pdpj", "documentos/lista_normal.json"))
    _pagina_1()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        df = _mk_scraper().documentos(PROC)

    assert _chamadas(endpoint) == 2
    assert df["motivo_falha"].isna().all()


@pytest.mark.parametrize("status", [502, 403])
@responses.activate
def test_500_com_falha_da_propria_pesquisa_retenta_pelo_perfil(status):
    endpoint = f"{BASE_URL}/processos/{PROC}/partes"
    _mock(endpoint, status=500)
    _mock(PESQUISA, status=status)

    with pytest.warns(UserWarning, match="retry_esgotado_500"):
        df = _mk_scraper().partes(PROC)

    assert _chamadas(endpoint) == 6
    # Uma tentativa só na confirmação, mesmo com status retentável.
    assert _chamadas(PESQUISA) == 1
    assert df["motivo_falha"].tolist() == ["retry_esgotado_500"]


@responses.activate
def test_500_com_pesquisa_401_interrompe():
    _mock(f"{BASE_URL}/processos/{PROC}/movimentos", status=500)
    _mock(PESQUISA, status=401)

    with pytest.raises(requests.HTTPError) as erro:
        _mk_scraper().movimentos(PROC)

    assert erro.value.response.status_code == 401


@responses.activate
def test_502_nao_dispara_a_confirmacao():
    endpoint = f"{BASE_URL}/processos/{PROC}/partes"
    _mock(endpoint, status=502)

    with pytest.warns(UserWarning, match="retry_esgotado_502"):
        _mk_scraper().partes(PROC)

    assert _chamadas(endpoint) == 6
    assert _chamadas(PESQUISA) == 0


@responses.activate
def test_confirmacao_vale_por_processo():
    """Cada processo tem a própria confirmação; a do primeiro não vale para o segundo."""
    _mock(f"{BASE_URL}/processos/{OUTRO}/documentos", status=500)
    _mock(PESQUISA, status=404, body=SEM_REGISTROS)
    _mock(f"{BASE_URL}/processos/{PROC}/documentos", status=500)
    _pagina_1()

    with pytest.warns(UserWarning, match="2 consulta"):
        df = _mk_scraper().documentos([OUTRO, PROC])

    assert df["motivo_falha"].tolist() == ["nao_encontrado", "retry_esgotado_500"]
    assert _chamadas(PESQUISA) == 2


# ---------------------------------------------------------------------
# 404 sem o corpo medido não é "sem registros"
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "corpo",
    ["<html>Not Found</html>", json.dumps({"code": 404, "message": "Recurso inexistente"}), ""],
    ids=["html", "outra_mensagem", "vazio"],
)
@responses.activate
def test_pesquisa_404_sem_o_corpo_medido_levanta(corpo):
    """Um 404 de roteamento (URL base trocada, gateway) não pode virar busca vazia."""
    _mock(PESQUISA, status=404, body=corpo)

    with pytest.raises(requests.HTTPError):
        _mk_scraper().pesquisa(tribunal="TRF1")


@responses.activate
def test_500_com_pesquisa_404_sem_o_corpo_medido_retenta_pelo_perfil():
    endpoint = f"{BASE_URL}/processos/{PROC}/documentos"
    _mock(endpoint, status=500)
    _mock(PESQUISA, status=404, body="<html>Not Found</html>")

    with pytest.warns(UserWarning, match="retry_esgotado_500"):
        df = _mk_scraper().documentos(PROC)

    assert _chamadas(endpoint) == 6
    assert df["motivo_falha"].tolist() == ["retry_esgotado_500"]


@responses.activate
def test_existe_com_lista_500_com_pesquisa_404_sai_nao_encontrado(esperas_do_backoff):
    endpoint = f"{BASE_URL}/processos/{OUTRO}/existe"
    _mock(endpoint, status=500)
    _mock(PESQUISA, status=404, body=SEM_REGISTROS)

    with pytest.warns(UserWarning, match=f"processo {OUTRO}: nao_encontrado"):
        df = _mk_scraper().existe([OUTRO])

    assert _chamadas(endpoint) == 1
    assert df["existe"].tolist() == [None]
    assert df["motivo_falha"].tolist() == ["nao_encontrado"]
    esperas_do_backoff.assert_not_called()
