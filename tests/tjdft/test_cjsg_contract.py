"""Offline contract tests for TJDFT cjsg."""
import pandas as pd
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from tests._helpers import load_sample

BASE = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
CJSG_MIN_COLUMNS = {"processo", "ementa", "dataJulgamento", "dataPublicacao"}


def _payload(
    pesquisa: str,
    pagina: int,
    *,
    sinonimos: bool = True,
    espelho: bool = True,
    inteiro_teor: bool = False,
    tamanho_pagina: int = 10,
    termos_acessorios: list | None = None,
) -> dict:
    return {
        "query": pesquisa,
        "termosAcessorios": list(termos_acessorios) if termos_acessorios else [],
        "pagina": pagina,
        "tamanho": tamanho_pagina,
        "sinonimos": sinonimos,
        "espelho": espelho,
        "inteiroTeor": inteiro_teor,
        "retornaInteiroTeor": False,
        "retornaTotalizacao": True,
    }


def _add_page(pesquisa: str, pagina: int, sample_path: str, **kwargs) -> None:
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload(pesquisa, pagina, **kwargs))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjdft").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records without hitting the network again."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjdft").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjdft").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
