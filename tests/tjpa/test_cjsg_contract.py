"""Offline contract tests for TJPA cjsg.

TJPA's BFF paginates 0-based: user-facing ``paginas=1`` sends ``page=0``.
The contract asserts both the DataFrame schema and the JSON payload — in
particular that the 0-based conversion actually happens on the wire.
"""
import pandas as pd
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjpa.download import BASE_URL, build_cjsg_payload
from tests._helpers import load_sample

CJSG_MIN_COLUMNS = {
    "processo", "tipo", "classe", "assunto", "relator",
    "orgao_julgador_colegiado", "data_julgamento", "data_publicacao", "ementa",
}


def _add_page(pesquisa: str, pagina_1based: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjpa", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(
            build_cjsg_payload(pesquisa, pagina_0based=pagina_1based - 1)
        )],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query exercises the 1-based → 0-based conversion on both pages."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjpa").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single page scenario — asserts ``page=0`` is sent for ``paginas=1``."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjpa").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjpa").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
