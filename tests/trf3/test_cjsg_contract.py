"""Offline contract tests for TRF3 ``cjsg`` (busca de jurisprudência).

The HTTP flow is mocked with ``responses`` in order (``OrderedRegistry``):
opening GET, form POST (302 to page 1) and one GET per extra page. Bodies are
real pages captured by ``tests/fixtures/capture/trf3_cjsg.py``.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.courts.trf3.cjsg_download import BASE_URL, INDEX_URL, SEARCH_URL, build_cjsg_payload
from tests._helpers import assert_no_mojibake
from tests.trf3._cjsg_mock import HTML, add_page, add_search, sample

CJSG_MIN_COLUMNS = {
    "processo", "classe", "orgao_julgador", "relator", "relator_acordao",
    "data_julgamento", "data_publicacao", "meio_publicacao", "ementa",
    "base", "url_inteiro_teor", "inteiro_teor",
}
SEMESTRE = {"data_julgamento_inicio": "2026-01-01", "data_julgamento_fim": "2026-06-30"}


def _semestre(pesquisa: str, base: str = "acordaos") -> dict[str, str]:
    """POST body for ``SEMESTRE``: julgamento between 01/01/2026 and 30/06/2026."""
    return build_cjsg_payload(pesquisa, base=base, data_inicial="01/01/2026", data_final="30/06/2026")


@responses.activate(registry=OrderedRegistry)
def test_cjsg_typical_com_paginacao(mocker):
    """Two pages: page 1 comes from the POST redirect, page 2 from ``np=2``."""
    mocker.patch("time.sleep")
    add_search(_semestre("medicamento"), "results_normal_page_01.html")
    add_page(2, "results_normal_page_02.html")

    df = jus.scraper("trf3").cjsg("medicamento", paginas=range(1, 3), **SEMESTRE)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) == 20
    assert df["processo"].is_unique
    assert (df["base"] == "acordaos").all()
    assert df["ementa"].notna().all() and df["inteiro_teor"].notna().all()
    assert all(isinstance(d, dt.date) for d in df["data_julgamento"])
    assert df["processo"].str.fullmatch(r"\d{7}-\d{2}\.\d{4}\.4\.03\.\d{4}").all()
    assert_no_mojibake(" ".join(df["ementa"]), contexto="ementas TRF3 cjsg")
    assert len(responses.calls) == 4


@responses.activate(registry=OrderedRegistry)
def test_cjsg_relator_para_acordao_e_publicacao(mocker):
    """The first sample row has a ``relator para acórdão`` and a DJEN publication."""
    mocker.patch("time.sleep")
    add_search(_semestre("medicamento"), "results_normal_page_01.html")

    df = jus.scraper("trf3").cjsg("medicamento", paginas=1, **SEMESTRE)

    primeira = df.iloc[0]
    assert primeira["processo"] == "5001743-27.2026.4.03.0000"
    assert primeira["classe"] == "AI - AGRAVO DE INSTRUMENTO"
    assert primeira["orgao_julgador"] == "3ª Turma"
    assert primeira["relator"] == "Desembargador Federal NERY DA COSTA JUNIOR"
    assert primeira["relator_acordao"] == "Desembargadora Federal CONSUELO YATSUDA MOROMIZATO YOSHIDA"
    assert primeira["data_julgamento"] == dt.date(2026, 6, 30)
    assert primeira["data_publicacao"] == dt.date(2026, 7, 7)
    assert primeira["meio_publicacao"] == "DJEN"
    assert primeira["url_inteiro_teor"].endswith("processo=50017432720264030000")
    # O termo pesquisado vem destacado com <em> no meio da frase; não pode partir a linha.
    assert "obtenção do medicamento Dordaviprona" in primeira["ementa"]
    assert primeira["ementa"].startswith("PODER JUDICIÁRIO\n")
    assert "Relatora do Acórdão" in primeira["inteiro_teor"]
    assert df["meio_publicacao"].isin({"DJEN", "Intimação via sistema"}).all()


@responses.activate(registry=OrderedRegistry)
def test_cjsg_single_page_paginas_none(mocker):
    """``paginas=None`` reads the total (2 documents) and stops after the POST."""
    mocker.patch("time.sleep")
    add_search(build_cjsg_payload(numero_processo="5001743-27.2026.4.03.0000"), "single_page.html")

    df = jus.scraper("trf3").cjsg(numero_processo="5001743-27.2026.4.03.0000")

    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) == 2
    assert (df["processo"] == "5001743-27.2026.4.03.0000").all()
    assert len(responses.calls) == 3


@responses.activate(registry=OrderedRegistry)
def test_cjsg_no_results(mocker):
    """Zero hits returns an empty DataFrame without requesting other pages."""
    mocker.patch("time.sleep")
    add_search(
        _semestre("juscraper_probe_zero_hits_xyzqwe"),
        "no_results.html",
    )

    df = jus.scraper("trf3").cjsg("juscraper_probe_zero_hits_xyzqwe", **SEMESTRE)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert len(responses.calls) == 3


@pytest.mark.parametrize(
    ("base", "sample_name", "orgao_preenchido", "tem_url"),
    [
        ("turmas_recursais", "turmas_recursais_page_01.html", True, True),
        ("monocraticas", "monocraticas_page_01.html", False, False),
        ("monocraticas_turmas_recursais", "monocraticas_turmas_recursais_page_01.html", False, False),
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_outras_bases(mocker, base, sample_name, orgao_preenchido, tem_url):
    """Each base opens its own tab and, for monocráticas, sends its origin box."""
    mocker.patch("time.sleep")
    add_search(_semestre("medicamento", base=base), sample_name, base=base)

    df = jus.scraper("trf3").cjsg("medicamento", base=base, paginas=1, **SEMESTRE)

    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) == 10
    assert (df["base"] == base).all()
    assert df["ementa"].notna().all()
    assert df["data_julgamento"].notna().all()
    assert df["orgao_julgador"].notna().all() == orgao_preenchido
    assert df["url_inteiro_teor"].notna().all() == tem_url
    assert responses.calls[0].request.url == INDEX_URL.format(indice={"turmas_recursais": 1}.get(base, 2))


def test_cjsg_parse_layout_antigo():
    """2012 layout: ``e-DJF3 Judicial 1 DATA:...`` without a space, órgão in words."""
    df = jus.scraper("trf3").cjsg_parse([sample("acordaos_2012.html").decode("utf-8")])

    assert len(df) == 10
    primeira = df.iloc[0]
    assert primeira["meio_publicacao"] == "e-DJF3 Judicial 1"
    assert primeira["data_publicacao"] == dt.date(2012, 12, 19)
    assert primeira["data_julgamento"] == dt.date(2012, 12, 13)
    assert primeira["orgao_julgador"] == "TERCEIRA TURMA"
    assert primeira["relator"] == "DESEMBARGADOR FEDERAL CARLOS MUTA"
    assert df["data_publicacao"].notna().all()


@responses.activate(registry=OrderedRegistry)
def test_cjsg_pagina_sem_a_primeira_descarta_a_resposta_do_post(mocker):
    """Asking only page 2 still runs the search; the POST body (page 1) is dropped."""
    mocker.patch("time.sleep")
    add_search(_semestre("medicamento"), "results_normal_page_01.html")
    add_page(2, "results_normal_page_02.html")

    brutos = jus.scraper("trf3").cjsg_download("medicamento", paginas=[2], **SEMESTRE)

    assert brutos == [sample("results_normal_page_02.html").decode("utf-8")]


@responses.activate(registry=OrderedRegistry)
def test_cjsg_paginas_alem_do_total_nao_sao_requisitadas(mocker):
    """The single-page search has 1 page; pages 2 and 3 are skipped without a request."""
    mocker.patch("time.sleep")
    add_search(build_cjsg_payload(numero_processo="5001743-27.2026.4.03.0000"), "single_page.html")

    df = jus.scraper("trf3").cjsg(numero_processo="5001743-27.2026.4.03.0000", paginas=range(1, 4))

    assert len(df) == 2
    assert len(responses.calls) == 3


@responses.activate(registry=OrderedRegistry)
def test_cjsg_sessao_expirada_levanta(mocker):
    """A redirect to ``Home/SessaoExpirada`` is an error, not an empty result."""
    mocker.patch("time.sleep")
    responses.add(responses.GET, INDEX_URL.format(indice=0), body=sample("index_acordaos.html"), content_type=HTML)
    responses.add(
        responses.POST, SEARCH_URL, status=302,
        headers={"Location": "/jurisprudencia/Home/SessaoExpirada"},
    )
    responses.add(responses.GET, BASE_URL + "Home/SessaoExpirada", body=b"<html></html>", content_type=HTML)

    with pytest.raises(RuntimeError, match="sessão expirada"):
        jus.scraper("trf3").cjsg("medicamento", paginas=1)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_bloqueio_akamai_levanta_bot_challenge(mocker):
    """The Akamai 403 ``Access Denied`` stops at the first request, without retry."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        INDEX_URL.format(indice=0),
        status=403,
        body=b"<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY><H1>Access Denied</H1>"
             b" Reference&#32;&#35;18&#46;27f62917&#46;1779623119&#46;a59b1f4c</BODY></HTML>",
        content_type=HTML,
    )

    with pytest.raises(BotChallengeBlockedError) as exc_info:
        jus.scraper("trf3").cjsg("medicamento", paginas=1)

    assert exc_info.value.reference == "18.27f62917.1779623119.a59b1f4c"
    assert len(responses.calls) == 1
