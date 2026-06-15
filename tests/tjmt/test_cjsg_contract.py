"""Offline contract tests for TJMT cjsg."""
import json

import pandas as pd
import responses
from responses.matchers import header_matcher, query_param_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample

CONFIG_URL = "https://jurisprudencia.tjmt.jus.br/assets/config/config.json"
API_URL = "https://hellsgate-preview.tjmt.jus.br/jurisprudencia/api/Consulta"
CJSG_MIN_COLUMNS = {"processo", "ementa", "relator", "orgao_julgador", "data_julgamento"}


def _params(
    pesquisa: str,
    pagina: int,
    *,
    tamanho_pagina: int = 10,
    tipo_consulta: str = "Acordao",
    data_julgamento_inicio: str = "",
    data_julgamento_fim: str = "",
    relator: str = "",
    orgao_julgador: str = "",
    tipo_processo: str = "",
    thesaurus: bool = False,
) -> dict:
    return {
        "filtro.isBasica": "true",
        "filtro.indicePagina": str(pagina),
        "filtro.quantidadePagina": str(tamanho_pagina),
        "filtro.tipoConsulta": tipo_consulta,
        "filtro.termoDeBusca": pesquisa,
        "filtro.area": "",
        "filtro.numeroProtocolo": "",
        "filtro.periodoDataDe": data_julgamento_inicio,
        "filtro.periodoDataAte": data_julgamento_fim,
        "filtro.tipoBusca": "1",
        "filtro.relator": relator,
        "filtro.julgamento": "",
        "filtro.orgaoJulgador": orgao_julgador,
        "filtro.colegiado": "",
        "filtro.localConsultaAcordao": "",
        "filtro.fqOrgaoJulgador": "",
        "filtro.fqTipoProcesso": "",
        "filtro.fqRelator": "",
        "filtro.fqJulgamento": "",
        "filtro.fqAssunto": "",
        "filtro.ordenacao.ordenarPor": "DataDecrescente",
        "filtro.ordenacao.ordenarDataPor": "Julgamento",
        "filtro.tipoProcesso": tipo_processo,
        "filtro.thesaurus": str(thesaurus).lower(),
        "filtro.fqTermos": "",
    }


def _add_config() -> None:
    responses.add(
        responses.GET,
        CONFIG_URL,
        body=load_sample("tjmt", "cjsg/config.json"),
        status=200,
        content_type="application/json",
    )


def _add_page(pesquisa: str, pagina: int, sample_path: str, **kwargs) -> None:
    token = json.loads(load_sample("tjmt", "cjsg/config.json"))["api_hellsgate_token"]
    responses.add(
        responses.GET,
        API_URL,
        body=load_sample("tjmt", sample_path),
        status=200,
        content_type="application/json",
        match=[
            query_param_matcher(_params(pesquisa, pagina, **kwargs)),
            header_matcher({"Token": token}, strict_match=False),
        ],
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query fetches config.json and then API pages."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjmt").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate(registry=OrderedRegistry)
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjmt").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
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
