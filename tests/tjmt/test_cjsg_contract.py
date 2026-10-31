"""Contratos offline do cjsg do TJMT."""
import json

import pandas as pd
import responses
from responses.matchers import query_param_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample

HOME_URL = "https://jurisprudencia.tjmt.jus.br/"
CHUNK_URL = "https://jurisprudencia.tjmt.jus.br/assets/chunk-contract.js"
API_URL = "https://hellsgate.tjmt.jus.br/jurisprudencia/consulta"
TEST_TOKEN = "synthetic-tjmt-token"
CJSG_MIN_COLUMNS = {"processo", "ementa", "relator", "orgao_julgador", "data_julgamento"}


def _params(
    pesquisa: str,
    pagina: int,
    *,
    tamanho_pagina: int = 10,
    tipo_consulta: str = "Acordao",
    data_publicacao_inicio: str = "",
    data_publicacao_fim: str = "",
    relator: str = "",
    orgao_julgador: str = "",
    tipo_processo: str = "",
    thesaurus: bool = False,
) -> dict:
    params = {
        "indicePagina": str(pagina - 1),
        "quantidadePagina": str(tamanho_pagina),
        "tipoConsulta": "1" if tipo_consulta == "Acordao" else "2",
        "termoDeBusca": pesquisa,
        "tipoBusca": "1",
        "OrdenarPor": "Relevancia",
        "Decrescente": "true",
        "thesaurus": str(thesaurus).lower(),
        "exibirArquivados": "true",
    }
    if relator:
        params["fqRelator"] = relator.upper()
    if orgao_julgador:
        params["fqOrgaoJulgador"] = orgao_julgador.upper()
    if tipo_processo:
        params["tipoProcesso"] = {"Criminal": "1", "Civel": "2", "Cível": "2"}[tipo_processo]
    if data_publicacao_inicio:
        params["periodoDataDe"] = data_publicacao_inicio
    if data_publicacao_fim:
        params["periodoDataAte"] = data_publicacao_fim
    return params


def _add_config() -> None:
    responses.add(
        responses.GET,
        HOME_URL,
        body='<html><script src="/assets/main-contract.js"></script></html>',
        status=200,
        content_type="text/html",
    )
    responses.add(
        responses.GET,
        "https://jurisprudencia.tjmt.jus.br/assets/main-contract.js",
        body='import "./chunk-contract.js";',
        status=200,
        content_type="application/javascript",
    )
    responses.add(
        responses.GET,
        CHUNK_URL,
        body=(
            'const config = { api_url: '
            f'"{API_URL.removesuffix("/consulta")}", '
            f'api_hellsgate_token: "{TEST_TOKEN}" }};'
        ),
        status=200,
        content_type="application/javascript",
    )


def _add_page(pesquisa: str, pagina: int, sample_path: str, **kwargs) -> None:
    body = json.loads(load_sample("tjmt", sample_path))
    responses.add(
        responses.GET,
        API_URL,
        json=body,
        status=200,
        content_type="application/json",
        match=[
            query_param_matcher(_params(pesquisa, pagina, **kwargs)),
        ],
    )

@responses.activate(registry=OrderedRegistry)
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query fetches config.json and then API pages."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_01.json")

    df = jus.scraper("tjmt").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    api_request = next(
        call.request for call in responses.calls if call.request.url.startswith(API_URL)
    )
    assert api_request.headers["Token"] == TEST_TOKEN


@responses.activate(registry=OrderedRegistry)
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page(
        "mandado de seguranca",
        1,
        "cjsg/single_page.json",
        tipo_consulta="DecisaoMonocratica",
    )

    df = jus.scraper("tjmt").cjsg(
        "mandado de seguranca",
        paginas=1,
        tipo_consulta="DecisaoMonocratica",
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate(registry=OrderedRegistry)
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjmt").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == [
        "id",
        "tipo",
        "ementa",
        "observacao",
        "processo",
        "classe",
        "assunto",
        "tipo_acao",
        "tipo_processo",
        "relator",
        "redator_designado",
        "orgao_julgador",
        "sigla_classe_feito",
        "data_julgamento",
        "data_publicacao",
        "instancia",
        "origem",
        "julgamento",
    ]
