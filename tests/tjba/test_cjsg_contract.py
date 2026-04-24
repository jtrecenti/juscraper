"""Offline contract tests for TJBA cjsg."""
import pandas as pd
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjba.download import FILTER_QUERY
from tests._helpers import load_sample

BASE = "https://jurisprudenciaws.tjba.jus.br/graphql"
CJSG_MIN_COLUMNS = {"processo", "relator", "orgao_julgador", "classe", "data_publicacao", "ementa"}


def _decisao_filter(
    pesquisa: str,
    *,
    numero_recurso: str | None = None,
    orgaos: list | None = None,
    relatores: list | None = None,
    classes: list | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    segundo_grau: bool = True,
    turmas_recursais: bool = True,
    tipo_acordaos: bool = True,
    tipo_decisoes_monocraticas: bool = True,
    ordenado_por: str = "dataPublicacao",
) -> dict:
    filtro = {
        "assunto": pesquisa,
        "orgaos": orgaos or [],
        "relatores": relatores or [],
        "classes": classes or [],
        "dataInicial": f"{data_publicacao_inicio}T03:00:00.000Z"
        if data_publicacao_inicio
        else "1980-02-01T03:00:00.000Z",
        "segundoGrau": segundo_grau,
        "turmasRecursais": turmas_recursais,
        "tipoAcordaos": tipo_acordaos,
        "tipoDecisoesMonocraticas": tipo_decisoes_monocraticas,
        "ordenadoPor": ordenado_por,
    }
    if data_publicacao_fim:
        filtro["dataFinal"] = f"{data_publicacao_fim}T03:00:00.000Z"
    if numero_recurso:
        filtro["numeroRecurso"] = numero_recurso
    return filtro


def _payload(
    pesquisa: str,
    page_number: int,
    *,
    items_per_page: int = 10,
    **filters,
) -> dict:
    return {
        "operationName": "filter",
        "variables": {
            "decisaoFilter": _decisao_filter(pesquisa, **filters),
            "pageNumber": page_number,
            "itemsPerPage": items_per_page,
        },
        "query": FILTER_QUERY,
    }


def _add_page(pesquisa: str, page_number: int, sample_path: str, **kwargs) -> None:
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjba", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload(pesquisa, page_number, **kwargs))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 0, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 1, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjba").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single requested page uses pageNumber 0 in the GraphQL payload."""
    mocker.patch("time.sleep")
    _add_page("consumidor", 0, "cjsg/single_page.json")

    df = jus.scraper("tjba").cjsg("consumidor", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 0, "cjsg/no_results.json")

    df = jus.scraper("tjba").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
