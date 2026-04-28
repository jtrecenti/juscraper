"""Offline contract tests for TJSP cposg (``method='html'`` and ``'api'``).

HTML flow: GET ``cposg/open.do`` → GET ``cposg/search.do`` → Caso 3
(resposta simples) or Caso 1/2 (listagem/modal). The CNJ used here lands
in Caso 3 — the search response itself contains the process details and
the scraper saves it under the ``cdProcesso`` value.

API flow: a single GET ``processo/cposg/search/numproc/{id}``. The parse
manager only globs ``**/*.html`` today (``cposg_parse_single_json`` is a
stub — see the follow-up issue), so ``method='api'`` ends up returning
an empty DataFrame. This contract captures that behaviour explicitly so a
future fix trips the assertion instead of the test silently passing with
a different payload.
"""
import pandas as pd
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

ESAJ = "https://esaj.tjsp.jus.br"
API = "https://api.tjsp.jus.br"

CNJ = "1000149-71.2024.8.26.0346"
CNJ_DIGITS = "10001497120248260346"

CPOSG_BASICOS_MIN = {"id_original", "classe", "status"}


# ---------- method='html' -----------------------------------------------

@responses.activate
def test_cposg_html_simple_response(tmp_path, mocker):
    """HTML flow — Caso 3 (resposta simples): search.do has the process details."""
    mocker.patch("time.sleep")

    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/open.do",
        body=load_sample_bytes("tjsp", "cposg/open.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"gateway": "true"})],
    )
    search_params = {
        "conversationId": "",
        "paginaConsulta": "1",
        "localPesquisa.cdLocal": "-1",
        "cbPesquisa": "NUMPROC",
        "tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": "1000149-71.2024",
        "foroNumeroUnificado": "0346",
        "dePesquisaNuUnificado": CNJ,
        "dePesquisa": "",
        "uuidCaptcha": "",
        "pbEnviar": "Pesquisar",
    }
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "cposg/search_listagem.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(search_params)],
    )

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="html")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert CPOSG_BASICOS_MIN <= set(df.columns)


# ---------- method='api' ------------------------------------------------

@responses.activate
def test_cposg_api_returns_empty_dataframe(tmp_path, mocker):
    """API flow fetches search/numproc then returns an empty DataFrame.

    Contract documents the current behaviour: ``cposg_download_api`` saves
    JSON but ``cposg_parse_manager`` only globs ``**/*.html`` (no JSON
    branch), so no rows are parsed. When the stub
    ``cposg_parse_single_json`` is implemented and ``cposg_parse_manager``
    is widened to consume JSON, rewrite this test to assert the real schema.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{API}/processo/cposg/search/numproc/{CNJ_DIGITS}",
        body=load_sample("tjsp", "cposg/api_search.json"),
        status=200,
        content_type="application/json",
    )

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="api")

    assert isinstance(df, pd.DataFrame)
    assert df.empty  # see docstring — follow-up issue pending
