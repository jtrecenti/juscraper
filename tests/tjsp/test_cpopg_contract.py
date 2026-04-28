"""Offline contract tests for TJSP cpopg (both ``method='html'`` and ``'api'``).

Mocks the request flows against samples captured by
``tests/fixtures/capture/tjsp.py``. Validates that the public ``.cpopg()``
call returns a dict of DataFrames with the expected keys and minimum
schema, for both transports.

HTML flow: GET ``cpopg/search.do?…`` → scraper extracts one
``processo.codigo`` → saves the search response itself (the eSAJ returns
the process details directly when the CNJ is unique).

API flow: GET ``processo/cpopg/search/numproc/{id}`` → POST
``processo/cpopg/dadosbasicos/{cd}`` → four GETs for partes/movimentacao/
incidente/audiencia. Order is not enforced via ``OrderedRegistry`` because
it's an implementation detail — ``responses`` matchers already pin each
endpoint to its sample.
"""
import pandas as pd
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

ESAJ = "https://esaj.tjsp.jus.br"
API = "https://api.tjsp.jus.br"

CNJ = "1000149-71.2024.8.26.0346"
CD_PROCESSO = "9M0002CYG0000"
CNJ_DIGITS = "10001497120248260346"

# Schema keys differ between HTML and API transports by design: the HTML
# parse collapses 'movimentacao' into 'movimentacoes' and groups 'peticoes
# diversas'; the API parse keeps the singular resource names from the JSON.
CPOPG_HTML_KEYS = {"basicos", "partes", "movimentacoes", "peticoes_diversas"}
CPOPG_API_KEYS = {"basicos", "partes", "movimentacao", "incidente", "audiencia"}
CPOPG_BASICOS_MIN = {"id_processo", "classe", "assunto"}


# ---------- method='html' -----------------------------------------------

@responses.activate
def test_cpopg_html_single_match(tmp_path, mocker):
    """HTML flow: search.do returns the process page directly (1 match)."""
    mocker.patch("time.sleep")
    search_params = {
        "conversationId": "",
        "cbPesquisa": "NUMPROC",
        "numeroDigitoAnoUnificado": "1000149-71.2024",
        "foroNumeroUnificado": "0346",
        "dadosConsulta.valorConsultaNuUnificado": CNJ,
        "dadosConsulta.valorConsulta": "",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
    }
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/search.do",
        body=load_sample_bytes("tjsp", "cpopg/search.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(search_params)],
    )

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ, method="html")

    assert isinstance(result, dict)
    assert CPOPG_HTML_KEYS <= set(result.keys())
    basicos = result["basicos"]
    assert isinstance(basicos, pd.DataFrame)
    assert CPOPG_BASICOS_MIN <= set(basicos.columns)
    assert len(basicos) == 1
    assert basicos.iloc[0]["id_processo"] == CNJ


# ---------- method='api' ------------------------------------------------

@responses.activate
def test_cpopg_api(tmp_path, mocker):
    """API flow: search/numproc → dadosbasicos → 4 component GETs."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{API}/processo/cpopg/search/numproc/{CNJ_DIGITS}",
        body=load_sample("tjsp", "cpopg/api_search.json"),
        status=200,
        content_type="application/json",
    )
    responses.add(
        responses.POST,
        f"{API}/processo/cpopg/dadosbasicos/{CD_PROCESSO}",
        body=load_sample("tjsp", "cpopg/api_dadosbasicos.json"),
        status=200,
        content_type="application/json",
    )
    for comp in ("partes", "movimentacao", "incidente", "audiencia"):
        responses.add(
            responses.GET,
            f"{API}/processo/cpopg/{comp}/{CD_PROCESSO}",
            body=load_sample("tjsp", f"cpopg/api_{comp}.json"),
            status=200,
            content_type="application/json",
        )

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ, method="api")

    assert isinstance(result, dict)
    assert CPOPG_API_KEYS <= set(result.keys())
    basicos = result["basicos"]
    assert isinstance(basicos, pd.DataFrame)
