"""Offline contract tests for TJRN cjsg.

TJRN serves the Elasticsearch-backed ``jurisprudencia.tjrn.jus.br/api/pesquisar``
endpoint. The contract asserts the DataFrame schema the parser returns and the
JSON payload the scraper sends, page-by-page.
"""
import pandas as pd
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjrn.download import BASE_URL, build_cjsg_payload
from tests._helpers import load_sample

CJSG_MIN_COLUMNS = {
    "processo", "classe", "orgao_julgador", "colegiado",
    "relator", "tipo_decisao", "data_julgamento", "ementa",
}


def _add_page(pesquisa: str, pagina: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(pesquisa, page=pagina))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjrn").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records without further requests."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjrn").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjrn").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
