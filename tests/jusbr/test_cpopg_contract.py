"""Offline contract tests for JusbrScraper.cpopg.

Fluxo real do ``cpopg`` (de ``aggregators/jusbr/client.py``):

1. Para cada CNJ no input:
   a. ``clean_cnj`` reduz a 20 digitos. Se vazio, fallback ``CNJ Invalido``
      (sem HTTP).
   b. ``GET /api/v2/processos/?numeroProcesso=<cnj_limpo>`` -> lista.
      Se ``content`` vazio, fallback ``Nao encontrado na lista inicial``.
   c. Para cada item na lista, ``GET /api/v2/processos/<numeroProcesso>``
      -> detalhes; row e ``parse_process_details_response``.
2. ``processo`` (canonico do projeto) aparece em **toda** linha — happy
   path via ``parse_process_details_response``, fallbacks injetam
   manualmente (followup 2 da #141). ``processo_pesquisado`` continua
   presente em fallbacks como sinonimo historico (flui via
   ``extra='allow'`` no schema). A reordenacao ``[processo_pesquisado,
   ...resto]`` so dispara quando o fallback ocorre.

Samples sao capturados via ``tests/fixtures/capture/jusbr.py`` (regra do
projeto: nunca sintetizar a mao).
"""
import json

import jwt
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample

LIST_URL = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"
DETAILS_URL_PREFIX = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"
HMAC_KEY = "0123456789abcdef0123456789abcdef-test"

# Constantes neutras coordenadas com o capture script. Quando o capture script
# sanitiza um CNJ real, substitui por estes valores; os testes batem nos mesmos.
NEUTRAL_CNJ_1 = "0000000-00.0000.0.00.0000"
NEUTRAL_CNJ_1_DIGITS = "00000000000000000000"
NEUTRAL_CNJ_2 = "1111111-11.1111.1.11.1111"
NEUTRAL_CNJ_2_DIGITS = "11111111111111111111"


def _fake_jwt() -> str:
    encoded: str = jwt.encode({"sub": "tester", "exp": 9999999999}, HMAC_KEY, algorithm="HS256")
    return encoded


def _authenticated_scraper(sleep_time: float = 0.0):
    scraper = jus.scraper("jusbr", sleep_time=sleep_time)
    scraper.auth(_fake_jwt())
    return scraper


def _numero_oficial_from_sample(sample_relpath: str) -> str:
    """Extrai o ``numeroProcesso`` do primeiro item de um sample de lista.

    Usar o valor do sample (em vez de hardcode) deixa o contrato robusto a
    mudancas no CNJ neutro adotado pelo capture script.
    """
    data = json.loads(load_sample("jusbr", sample_relpath))
    numero: str = data["content"][0]["numeroProcesso"]
    return numero


@responses.activate(registry=OrderedRegistry)
def test_cpopg_typical_single_processo(mocker):
    """Um CNJ -> 1 lista + 1 detalhes -> DataFrame com colunas do parser."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    numero_oficial = _numero_oficial_from_sample("cpopg/typical_single.json")

    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("jusbr", "cpopg/typical_single.json"),
        status=200,
        content_type="application/json",
        match=[query_param_matcher({"numeroProcesso": NEUTRAL_CNJ_1_DIGITS})],
    )
    responses.add(
        responses.GET,
        f"{DETAILS_URL_PREFIX}{numero_oficial}",
        body=load_sample("jusbr", "cpopg/typical_single_details.json"),
        status=200,
        content_type="application/json",
    )

    df = scraper.cpopg(NEUTRAL_CNJ_1)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    # Happy path emite essas colunas (parse_process_details_response).
    assert {"processo", "numeroProcesso", "idCodexTribunal", "detalhes"} <= set(df.columns)
    # Sem fallback, processo_pesquisado nao aparece — primeira coluna e
    # ``processo`` (insertion order do dict do parser).
    assert df.columns[0] == "processo"
    assert df.iloc[0]["processo"] == NEUTRAL_CNJ_1_DIGITS


@responses.activate(registry=OrderedRegistry)
def test_cpopg_lista_de_cnjs(mocker):
    """``id_cnj`` como ``list[str]`` -> 2 listas + 2 detalhes em ordem."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    numero_1 = _numero_oficial_from_sample("cpopg/list_two_first.json")
    numero_2 = _numero_oficial_from_sample("cpopg/list_two_second.json")

    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("jusbr", "cpopg/list_two_first.json"),
        status=200,
        content_type="application/json",
        match=[query_param_matcher({"numeroProcesso": NEUTRAL_CNJ_1_DIGITS})],
    )
    responses.add(
        responses.GET,
        f"{DETAILS_URL_PREFIX}{numero_1}",
        body=load_sample("jusbr", "cpopg/list_two_first_details.json"),
        status=200,
        content_type="application/json",
    )
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("jusbr", "cpopg/list_two_second.json"),
        status=200,
        content_type="application/json",
        match=[query_param_matcher({"numeroProcesso": NEUTRAL_CNJ_2_DIGITS})],
    )
    responses.add(
        responses.GET,
        f"{DETAILS_URL_PREFIX}{numero_2}",
        body=load_sample("jusbr", "cpopg/list_two_second_details.json"),
        status=200,
        content_type="application/json",
    )

    df = scraper.cpopg([NEUTRAL_CNJ_1, NEUTRAL_CNJ_2])

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert {"processo", "numeroProcesso", "detalhes"} <= set(df.columns)
    assert sorted(df["processo"].tolist()) == sorted([NEUTRAL_CNJ_1_DIGITS, NEUTRAL_CNJ_2_DIGITS])


@responses.activate(registry=OrderedRegistry)
def test_cpopg_no_results(mocker):
    """Lista vazia (``content: []``) -> fallback com ``processo_pesquisado``."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("jusbr", "cpopg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[query_param_matcher({"numeroProcesso": NEUTRAL_CNJ_1_DIGITS})],
    )

    df = scraper.cpopg(NEUTRAL_CNJ_1)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    # Followup 2 da #141: ``processo`` (canonico) presente em fallbacks.
    assert {"processo", "processo_pesquisado", "status_consulta"} <= set(df.columns)
    # Fallback dispara a reordenacao -> primeira coluna e processo_pesquisado.
    assert df.columns[0] == "processo_pesquisado"
    assert df.iloc[0]["status_consulta"] == "Nao encontrado na lista inicial"
    assert df.iloc[0]["processo"] == NEUTRAL_CNJ_1_DIGITS
    assert df.iloc[0]["processo_pesquisado"] == NEUTRAL_CNJ_1_DIGITS


@responses.activate(registry=OrderedRegistry)
def test_cpopg_cnj_invalido_nao_dispara_http(mocker):
    """``clean_cnj("abcde")`` retorna ``""`` -> fallback sem HTTP."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    df = scraper.cpopg("abcde")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["status_consulta"] == "CNJ Invalido"
    # Followup 2 da #141: ambas as colunas presentes em fallback.
    assert df.iloc[0]["processo"] == "abcde"
    assert df.iloc[0]["processo_pesquisado"] == "abcde"
    # Nenhum responses.add foi feito; o fato do scraper nao tentar HTTP
    # e a propria assertiva (responses.activate falharia em request nao mockado).


def test_cpopg_sem_auth_levanta_runtime_error():
    """Sem ``auth(token)`` previo, ``cpopg`` aborta antes de qualquer HTTP."""
    scraper = jus.scraper("jusbr")
    with pytest.raises(RuntimeError, match="[Aa]utentica"):
        scraper.cpopg(NEUTRAL_CNJ_1)
