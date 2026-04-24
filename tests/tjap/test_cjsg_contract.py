"""Offline contract tests for TJAP cjsg."""
import pandas as pd
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from tests._helpers import load_sample

BASE = "https://tucujuris.tjap.jus.br/api/publico/consultar-jurisprudencia"
CJSG_MIN_COLUMNS = {"processo", "numero_acordao", "classe", "relator", "data_julgamento", "ementa"}


def _payload(
    pesquisa: str,
    *,
    offset: int = 0,
    orgao: str = "0",
    numero_processo: str | None = None,
    numero_acordao: str | None = None,
    numero_ano: str | None = None,
    palavras_exatas: bool = False,
    relator: str | None = None,
    secretaria: str | None = None,
    classe: str | None = None,
    votacao: str = "0",
    origem: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "orgao": orgao,
        "ementa": pesquisa,
        "votacao": votacao,
        "tipo_jurisprudencia": None,
    }
    if offset > 0:
        payload["offset"] = offset
    if numero_processo:
        payload["numeroCNJ"] = numero_processo
    if numero_acordao:
        payload["numeroAcordao"] = numero_acordao
    if numero_ano:
        payload["numeroAno"] = numero_ano
    if palavras_exatas:
        payload["palavrasExatas"] = True
    if relator:
        payload["relator"] = relator
    if secretaria:
        payload["secretaria"] = secretaria
    if classe:
        payload["classe"] = classe
    if origem:
        payload["origem"] = origem
    return payload


def _add_page(pesquisa: str, sample_path: str, **kwargs) -> None:
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjap", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload(pesquisa, **kwargs))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_page("dano moral", "cjsg/results_normal_page_01.json")
    _add_page("dano moral", "cjsg/results_normal_page_02.json", offset=20)

    df = jus.scraper("tjap").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", "cjsg/single_page.json")

    df = jus.scraper("tjap").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", "cjsg/no_results.json")

    df = jus.scraper("tjap").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
