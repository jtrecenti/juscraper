"""Offline contract tests for TJRR cjsg.

TJRR's flow runs entirely against ``/index.xhtml`` (JSF/PrimeFaces) and
distinguishes requests by HTTP method and body shape:

1. ``GET /index.xhtml`` — extracts ``ViewState`` and the dynamic JSF
   component IDs (``menuinicial:j_idtNNN``) the scraper needs to build
   the form body.
2. ``POST /index.xhtml`` form-urlencoded — initial search (page 1
   inline). Body carries every form default plus ``pesquisa``,
   ``ViewState``, dates, ``orgao_julgador``/``especie`` lists.
3. ``POST /index.xhtml`` partial-response — pagination via
   ``javax.faces.partial.ajax=true``. Response is XML with the result
   HTML wrapped inside a ``<![CDATA[...]]>`` block; the scraper extracts
   it with ``_extract_cdata``.

Because the same URL serves three request kinds, the contract uses
``OrderedRegistry`` so each ``responses.add`` call matches the next
request in sequence.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample, urlencoded_body_subset_matcher
from tests.tjrr._helpers import INDEX_URL, add_get_initial, get_datatable_id

CJSG_MIN_COLUMNS = {
    "processo", "classe", "relator", "orgao_julgador",
    "data_julgamento", "data_publicacao", "ementa",
}

_SAMPLES_DIR = Path(__file__).parent / "samples" / "cjsg"
pytestmark = pytest.mark.skipif(
    not (_SAMPLES_DIR / "step_01_consulta.html").exists(),
    reason=(
        "TJRR samples ainda não capturados — rode "
        "`python -m tests.fixtures.capture.tjrr` para popular "
        "tests/tjrr/samples/cjsg/."
    ),
)


def _add_post_initial(sample_path: str):
    """Initial form POST that returns the first page inline as HTML."""
    responses.add(
        responses.POST,
        INDEX_URL,
        body=load_sample("tjrr", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[urlencoded_body_subset_matcher({
            "menuinicial": "menuinicial",
        })],
    )


def _add_post_ajax(sample_path: str, first_offset: str):
    """Pagination POST (``javax.faces.partial.ajax=true``) returning XML.

    Pins the issue #287 layer-2 fix: the body must carry the full
    results-form context (``consultaAtual``, the search term), the
    PrimeFaces ``page`` behavior event and the absolute ``_first`` offset.
    The minimal payload that omitted them was silently ignored by the
    backend (always returned page 1). The datatable id is derived from the
    sample (never hardcoded), since the JSF number drifts between deploys.
    """
    dtid = get_datatable_id()
    responses.add(
        responses.POST,
        INDEX_URL,
        body=load_sample("tjrr", sample_path),
        status=200,
        content_type="application/xml; charset=UTF-8",
        match=[urlencoded_body_subset_matcher({
            "javax.faces.partial.ajax": "true",
            "javax.faces.behavior.event": "page",
            "formPesquisa:consultaAtual": "dano moral",
            f"{dtid}_first": first_offset,
        })],
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_typical_com_paginacao(mocker):
    """Page 2 brings *new* processos, not a re-fetch of page 1 (issue #287).

    Mirrors the live integration assertion offline: ``df_p1`` (GET + POST
    inicial) vs ``df_p2`` (GET + POST inicial + POST AJAX). The set
    difference pins the cursor actually advancing — a plain ``len`` check
    would pass even if page 2 merely repeated page 1 (the layer-2 bug).
    """
    mocker.patch("time.sleep")
    # df_p1: GET + POST inicial. df_p2: GET + POST inicial + POST AJAX.
    add_get_initial()
    _add_post_initial("cjsg/step_02_search.html")
    add_get_initial()
    _add_post_initial("cjsg/step_02_search.html")
    _add_post_ajax("cjsg/step_03_pagina_02.xml", "10")

    df_p1 = jus.scraper("tjrr").cjsg("dano moral", paginas=1)
    df_p2 = jus.scraper("tjrr").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df_p2, pd.DataFrame)
    assert set(df_p2.columns) >= CJSG_MIN_COLUMNS
    assert df_p2["processo"].notna().all(), "processo nulo em alguma linha"
    assert (df_p2["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )
    assert len(df_p2) > len(df_p1), "página 2 não acrescentou linhas"
    novos = set(df_p2["processo"]) - set(df_p1["processo"])
    assert novos, "página 2 não trouxe processos novos (paginação presa)"


@responses.activate(registry=OrderedRegistry)
def test_cjsg_single_page(mocker):
    """Single page scenario: GET + POST inicial only (no AJAX)."""
    mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial("cjsg/single_page.html")

    df = jus.scraper("tjrr").cjsg("usucapiao", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame.

    TJRR's backend silently ignores both unknown search terms and date
    filters when applied in isolation; the only combination that
    reliably yields zero rows is an improbable term *together with* an
    impossible date range. The capture script reproduces this combo
    on a fresh session.
    """
    mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial("cjsg/no_results.html")

    df = jus.scraper("tjrr").cjsg(
        "juscraperprobeztzeroxyz",
        paginas=1,
        data_julgamento_inicio="01/01/2099",
        data_julgamento_fim="31/12/2099",
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty
