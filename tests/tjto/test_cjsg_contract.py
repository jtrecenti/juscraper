"""Offline contract tests for TJTO cjsg.

The TJTO Solr search has no pre-request flow: the public ``cjsg`` POSTs
directly to ``consulta.php``. Pagination is offset-based: ``start=0`` for
page 1, ``start=20`` for page 2, etc.
"""
import pandas as pd
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjto.download import BASE_URL, build_cjsg_payload
from tests._helpers import load_sample

CJSG_FIELDS = {
    "processo", "uuid", "classe", "tipo_julgamento", "assunto",
    "competencia", "relator", "data_autuacao", "data_julgamento",
    "processo_link",
}


def _add_post(query: str, *, start: int, sample_path: str, instancia: str = "2") -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjto", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[urlencoded_params_matcher(
            build_cjsg_payload(query, start=start, tip_criterio_inst=instancia),
            allow_blank=True,
        )],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two pages: ``start=0`` then ``start=20`` (Solr offset)."""
    mocker.patch("time.sleep")
    _add_post("dano moral", start=0, sample_path="cjsg/results_normal_page_01.html")
    _add_post("dano moral", start=20, sample_path="cjsg/results_normal_page_02.html")

    df = jus.scraper("tjto").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_FIELDS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single-hit query: only one POST with ``start=0``."""
    mocker.patch("time.sleep")
    _add_post('"alimentos avoengos"', start=0, sample_path="cjsg/single_page.html")

    df = jus.scraper("tjto").cjsg('"alimentos avoengos"', paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_FIELDS <= set(df.columns)
    assert len(df) == 9


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame (not an error)."""
    mocker.patch("time.sleep")
    _add_post("juscraper_probe_zero_hits_xyzqwe", start=0,
              sample_path="cjsg/no_results.html")

    df = jus.scraper("tjto").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_uses_instancia_2(mocker):
    """The cjsg shortcut must always send ``tip_criterio_inst='2'``."""
    mocker.patch("time.sleep")
    _add_post("dano moral", start=0, sample_path="cjsg/results_normal_page_01.html")

    jus.scraper("tjto").cjsg("dano moral", paginas=1)

    body = responses.calls[0].request.body or ""
    assert "tip_criterio_inst=2" in body
