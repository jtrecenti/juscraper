"""Offline contract tests for TJPI cjsg.

TJPI is a GET endpoint with query-string parameters. The page count is
read from the last-page link (``»``) of the ``ul.pagination`` paginator;
``single_page`` has no paginator at all, which is the 1-page path.
"""
import logging

import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts.tjpi.download import BASE_URL, _get_total_pages, build_cjsg_params
from tests._helpers import load_sample

CJSG_MIN_COLUMNS = {"processo", "tipo", "classe", "assunto", "data_publicacao", "ementa"}


def _add_page(pesquisa: str, pagina: int, sample_path: str) -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params(pesquisa, page=pagina))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query exercises ``page=1`` and ``page=2`` query-string values."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.html")

    df = jus.scraper("tjpi").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single page scenario — sample has no pagination links; parser stops at 1."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca usucapiao extraordinario", 1, "cjsg/single_page.html")

    df = jus.scraper("tjpi").cjsg("mandado de seguranca usucapiao extraordinario", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_paginas_none_descobre_via_html(mocker):
    r"""``paginas=None`` exercises ``_get_total_pages`` against the HTML.

    The ``single_page`` sample has no ``ul.pagination``, so
    ``_get_total_pages`` returns 1. Only one request must hit the wire.
    """
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca usucapiao extraordinario", 1, "cjsg/single_page.html")

    df = jus.scraper("tjpi").cjsg(
        "mandado de seguranca usucapiao extraordinario", paginas=None,
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert len(responses.calls) == 1


@responses.activate
def test_cjsg_paginas_none_sem_contagem_levanta(mocker):
    """A first page without the result count cannot tell the total: raise, never estimate.

    The count ("de um total de N jurisprudência(s)") is the source of the
    total; without it, ``paginas=None`` used to download a single page in
    silence. The error comes after the first request and before any other.
    """
    mocker.patch("time.sleep")
    contagem = "de um total de <b>137865</b> jurisprudência(s)"
    html = load_sample("tjpi", "cjsg/results_normal_page_01.html")
    assert html.count(contagem) == 2
    responses.add(
        responses.GET,
        BASE_URL,
        body=html.replace(contagem, ""),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params("dano moral", page=1))],
    )

    with pytest.raises(ValueError, match="não traz a contagem"):
        jus.scraper("tjpi").cjsg("dano moral", paginas=None)

    assert len(responses.calls) == 1


@responses.activate
def test_cjsg_paginas_explicitas_sem_contagem_levanta(mocker):
    """Com ``paginas`` explícito, a contagem sai da menor página pedida, e sem ela o download para."""
    mocker.patch("time.sleep")
    contagem = "de um total de <b>137865</b> jurisprudência(s)"
    html = load_sample("tjpi", "cjsg/results_normal_page_02.html")
    assert contagem in html
    responses.add(
        responses.GET,
        BASE_URL,
        body=html.replace(contagem, ""),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params("dano moral", page=2))],
    )

    with pytest.raises(ValueError, match="não traz a contagem"):
        jus.scraper("tjpi").cjsg("dano moral", paginas=[3, 2])

    assert len(responses.calls) == 1


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.html")

    df = jus.scraper("tjpi").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def _paginas_pedidas() -> list[str]:
    return [chamada.request.params["page"] for chamada in responses.calls]


@responses.activate
def test_cjsg_download_alem_do_total_avisa_com_o_total_da_busca(mocker, caplog):
    """A página além do total responde "Sem resultados para:"; o total do aviso sai da página 1.

    ``no_results.html`` é a resposta real a uma busca vazia, que traz o mesmo
    marcador da resposta à página além do total.
    """
    mocker.patch("time.sleep")
    _add_page("dano moral", 10**6, "cjsg/no_results.html")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    total = _get_total_pages(load_sample("tjpi", "cjsg/results_normal_page_01.html"))

    with caplog.at_level(logging.WARNING, logger="juscraper.tjpi"):
        brutos = jus.scraper("tjpi").cjsg_download("dano moral", paginas=[10**6, 10**6 + 1])

    assert brutos == []
    assert total > 1
    assert caplog.messages == [f"TJPI: páginas 1000000, 1000001 fora do intervalo 1-{total}"]
    assert _paginas_pedidas() == ["1000000", "1"]


@responses.activate
def test_cjsg_download_pagina_2_de_busca_vazia_avisa_uma_pagina(mocker, caplog):
    """Busca sem resultados: a página 1 também responde "Sem resultados para:", e o total é 1."""
    mocker.patch("time.sleep")
    for pagina in (2, 1):
        _add_page("juscraper_probe_zero_hits_xyzqwe", pagina, "cjsg/no_results.html")

    with caplog.at_level(logging.WARNING, logger="juscraper.tjpi"):
        brutos = jus.scraper("tjpi").cjsg_download("juscraper_probe_zero_hits_xyzqwe", paginas=[2])

    assert brutos == []
    assert caplog.messages == ["TJPI: página 2 fora do intervalo 1-1"]
    assert _paginas_pedidas() == ["2", "1"]
