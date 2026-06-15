"""Offline contract: propagacao de ``id_cnj`` em ``JusbrScraper.cpopg``.

A "filter surface" do JusBR e minima — ``cpopg`` aceita so ``id_cnj`` (str ou
``list[str]``). Estes contratos garantem que:

1. CNJ formatado e limpo via ``clean_cnj`` antes de chegar na query string.
2. ``list[str]`` dispara N pares (lista, detalhes) na ordem da lista.
3. Kwargs desconhecidos sao rejeitados pelo Python puro hoje (``cpopg`` nao
   tem ``**kwargs``). Quando o wiring de ``InputCPOPGJusBR`` entrar como
   follow-up, o ``ValidationError`` do pydantic levanta antes — o teste
   continua passando.
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
    data = json.loads(load_sample("jusbr", sample_relpath))
    numero: str = data["content"][0]["numeroProcesso"]
    return numero


@responses.activate(registry=OrderedRegistry)
def test_cnj_formatado_e_limpo_antes_do_request(mocker):
    """CNJ com pontos/hifens chega ao backend so com digitos."""
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

    df = scraper.cpopg(NEUTRAL_CNJ_1)  # input com pontuacao
    # Se o matcher acima falhasse (CNJ chegou com pontuacao), responses
    # levantaria ConnectionError em vez de devolver o sample.
    assert isinstance(df, pd.DataFrame) and len(df) == 1


@responses.activate(registry=OrderedRegistry)
def test_lista_de_cnjs_propaga_cada_um(mocker):
    """``id_cnj=[A, B]`` produz 2 listas na ordem, cada uma com seu digito."""
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
    assert len(df) == 2


def test_kwarg_desconhecido_e_rejeitado():
    """``cpopg`` nao tem ``**kwargs`` -> Python puro levanta ``TypeError``.

    Quando ``InputCPOPGJusBR`` for wirado como follow-up, o
    ``ValidationError`` do pydantic vai levantar antes; ate la, o
    ``TypeError`` ja garante a rejeicao silenciosa.
    """
    scraper = jus.scraper("jusbr")
    scraper.auth(_fake_jwt())
    with pytest.raises(TypeError, match="filtro_inexistente"):
        scraper.cpopg(NEUTRAL_CNJ_1, filtro_inexistente="x")
