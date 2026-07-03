"""Offline contract tests for TJPE cjsg.

TJPE's cjsg flow is JSF/RichFaces-based and spans **three different
XHTML endpoints** under ``/consultajurisprudenciaweb/xhtml/consulta/``:

1. ``GET consulta.xhtml`` — extracts the JSF ``ViewState``.
2. ``POST consulta.xhtml`` — search submission. The response is either
   the *escolha* page (chooser between Acordaos and Decisoes
   Monocraticas, when ``tipo_decisao="todos"`` enables both checkboxes)
   or the results page directly (when a single ``tipo_decisao`` is
   selected).
3. ``POST escolhaResultado.xhtml`` — only used when escolha is shown:
   picks the result type and returns results page 1.
4. ``POST resultado.xhtml`` — RichFaces AJAX pagination
   (``AJAXREQUEST=_viewRoot``). Response is XML wrapping HTML inside a
   ``<![CDATA[...]]>`` block; the parser unwraps it.

Because the same URL (``consulta.xhtml``) serves both the GET and the
POST that returns either escolha or results, and the scraper threads
the ``ViewState`` between requests, the contract uses
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
from juscraper.courts.tjpe.download import BASE_URL
from tests._helpers import load_sample

CONSULTA_URL = f"{BASE_URL}/consulta.xhtml"
ESCOLHA_URL = f"{BASE_URL}/escolhaResultado.xhtml"
RESULTADO_URL = f"{BASE_URL}/resultado.xhtml"

CJSG_MIN_COLUMNS = {
    "processo", "classe", "assunto", "relator", "orgao_julgador",
    "data_julgamento", "data_publicacao", "ementa",
}

_SAMPLES_DIR = Path(__file__).parent / "samples" / "cjsg"
pytestmark = pytest.mark.skipif(
    not (_SAMPLES_DIR / "step_01_consulta.html").exists(),
    reason=(
        "TJPE samples ainda nao capturados — rode "
        "`python -m tests.fixtures.capture.tjpe` para popular "
        "tests/tjpe/samples/cjsg/."
    ),
)


def _add_get_consulta() -> None:
    """Initial GET on consulta.xhtml (carries ViewState the scraper extracts)."""
    responses.add(
        responses.GET,
        CONSULTA_URL,
        body=load_sample("tjpe", "cjsg/step_01_consulta.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_post_consulta(sample_path: str) -> None:
    """POST on consulta.xhtml — returns escolha page, results page, or zero hits."""
    responses.add(
        responses.POST,
        CONSULTA_URL,
        body=load_sample("tjpe", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_post_escolha(sample_path: str) -> None:
    """POST on escolhaResultado.xhtml — picks result type, returns results page 1."""
    responses.add(
        responses.POST,
        ESCOLHA_URL,
        body=load_sample("tjpe", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_post_ajax(sample_path: str) -> None:
    """POST on resultado.xhtml — AJAX pagination, returns RichFaces XML."""
    responses.add(
        responses.POST,
        RESULTADO_URL,
        body=load_sample("tjpe", sample_path),
        status=200,
        content_type="text/xml; charset=UTF-8",
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_escolha_typical(mocker):
    """4-call flow: GET consulta + POST consulta=escolha + POST escolha + AJAX page 2.

    Triggered by ``tipo_decisao="todos"``, which marks both
    ``tipoAcordao`` and ``tipoDecisaoMonocratica`` checkboxes — the
    backend then routes the response through the chooser page.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/step_02_escolha.html")
    _add_post_escolha("cjsg/step_03_resultado.html")
    _add_post_ajax("cjsg/step_04_pagina_02.xml")

    df = jus.scraper("tjpe").cjsg(
        "dano moral", paginas=range(1, 3), tipo_decisao="todos"
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )
    assert df["processo"].nunique() > 1, (
        "todos os processos iguais — paginacao suspeita"
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_simples_typical(mocker):
    """3-call flow: GET consulta + POST consulta=results + AJAX page 2.

    With the default ``tipo_decisao="acordaos"`` only one checkbox is
    marked, so the backend skips the chooser and returns the results
    page directly from the initial POST.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/simples_resultado.html")
    _add_post_ajax("cjsg/simples_pagina_02.xml")

    df = jus.scraper("tjpe").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )
    assert df["processo"].nunique() > 1, (
        "todos os processos iguais — paginacao suspeita"
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_no_results(mocker):
    """Zero-hit query: GET consulta + POST consulta=zero, no AJAX follow-up."""
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/no_results.html")

    df = jus.scraper("tjpe").cjsg("juscraperprobeztzeroxyz", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
