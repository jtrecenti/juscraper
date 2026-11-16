"""Offline contract tests for TJAL cjsg.

Mocks ``resultadoCompleta.do`` + ``trocaDePagina.do`` with captured samples
(see ``tests/fixtures/capture/tjal.py``) and asserts the public DataFrame
contract. Covers typical multi-page, single-page, and zero-result scenarios.
"""
import pandas as pd
import responses
from responses.matchers import query_param_matcher, urlencoded_params_matcher

import juscraper as jus
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_esaj_body

BASE = "https://www2.tjal.jus.br/cjsg"
CJSG_MIN_COLUMNS = {"processo", "cd_acordao", "cd_foro", "ementa"}


def _add_post(pesquisa: str, tipo_decisao: str = "acordao") -> None:
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjal", "cjsg/post_initial.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(make_esaj_body(pesquisa, tipo_decisao=tipo_decisao), allow_blank=True)],
    )


def _add_get(pagina: int, sample_path: str, tipo: str = "A") -> None:
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjal", sample_path),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[query_param_matcher({"tipoDeDecisao": tipo, "pagina": str(pagina)})],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(tmp_path, mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_post("dano moral")
    _add_get(1, "cjsg/results_normal_page_01.html")
    _add_get(2, "cjsg/results_normal_page_02.html")

    df = jus.scraper("tjal", download_path=str(tmp_path)).cjsg(
        "dano moral", paginas=range(1, 3)
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(tmp_path, mocker):
    """Query whose hits fit in one page skips the per-page loop."""
    mocker.patch("time.sleep")
    _add_post("usucapiao extraordinario predio rural familia")
    _add_get(1, "cjsg/single_page.html")

    df = jus.scraper("tjal", download_path=str(tmp_path)).cjsg(
        "usucapiao extraordinario predio rural familia", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(tmp_path, mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_post("juscraper_probe_zero_hits_xyzqwe")
    _add_get(1, "cjsg/no_results.html")

    df = jus.scraper("tjal", download_path=str(tmp_path)).cjsg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_monocratica_single_page(tmp_path, mocker):
    """Busca de monocráticas: ``D`` no POST e no GET, e o total vem do input ``-D``.

    O formulário do TJAL só mostra a caixa de acórdãos, mas o eSAJ responde à
    busca com ``tipoDecisaoSelecionados=D`` com a aba de monocráticas.
    """
    mocker.patch("time.sleep")
    _add_post("usucapiao predio rural", tipo_decisao="monocratica")
    _add_get(1, "cjsg/monocratica_single_page.html", tipo="D")

    df = jus.scraper("tjal", download_path=str(tmp_path)).cjsg(
        "usucapiao predio rural", tipo_decisao="monocratica"
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) == 2  # totalResultadoAbaRetornoFiltro-D no sample
    assert len(responses.calls) == 2  # POST + 1 GET: o total cabe em uma página
