"""Offline contract for ``DatajudScraper.listar_processos`` (issue #140).

Each test mocks the Elasticsearch endpoint at
``api-publica.datajud.cnj.jus.br/<alias>/_search`` and validates both the
JSON body sent (via ``json_params_matcher``) and the ``Authorization``
header. Multi-page tests use ``OrderedRegistry`` because page 2 carries
the ``search_after`` cursor extracted from the last hit of page 1.

The ``_payload`` helper imported from the capture script is the single
source of truth for the body shape — keeping capture and contract aligned
without introducing drift between three separate replicas of the
Elasticsearch DSL builder.

Samples are captured by ``python -m tests.fixtures.capture.datajud``.
"""
import json

import pandas as pd
import responses
from responses.matchers import header_matcher, json_params_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.aggregators.datajud.client import DatajudScraper
from tests._helpers import load_sample
from tests.fixtures.capture.datajud import build_payload as _payload

BASE = DatajudScraper.BASE_API_URL
API_KEY = DatajudScraper.DEFAULT_API_KEY
LISTAR_PROCESSOS_MIN_COLUMNS = {"numeroProcesso", "classe", "tribunal"}

# CNJ from the captured page-1 sample. Formatted form below; the client
# clean_cnj's it before sending in ``terms.numeroProcesso``.
CNJ_TJSP_FORMATTED = "1000413-22.2017.8.26.0415"
CNJ_TJSP_CLEAN = "10004132220178260415"


def _add_page(alias: str, sample_path: str, **payload_kwargs) -> None:
    responses.add(
        responses.POST,
        f"{BASE}/{alias}/_search",
        body=load_sample("datajud", sample_path),
        status=200,
        content_type="application/json",
        match=[
            json_params_matcher(_payload(**payload_kwargs)),
            header_matcher(
                {"Authorization": f"APIKey {API_KEY}"}, strict_match=False
            ),
        ],
    )


@responses.activate(registry=OrderedRegistry)
def test_listar_processos_typical_multi_page(mocker):
    """Two POSTs: page 1 with no ``search_after``; page 2 with the sort
    cursor lifted from page 1's last hit."""
    mocker.patch("time.sleep")
    sample_p1 = json.loads(
        load_sample("datajud", "listar_processos/results_normal_page_01.json")
    )
    last_sort = sample_p1["hits"]["hits"][-1]["sort"]

    _add_page(
        "api_publica_tjsp",
        "listar_processos/results_normal_page_01.json",
        tamanho_pagina=2,
    )
    _add_page(
        "api_publica_tjsp",
        "listar_processos/results_normal_page_02.json",
        tamanho_pagina=2,
        search_after=last_sort,
    )

    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP", paginas=range(1, 3), tamanho_pagina=2
    )

    assert isinstance(df, pd.DataFrame)
    assert LISTAR_PROCESSOS_MIN_COLUMNS <= set(df.columns)
    assert len(df) == 4


@responses.activate
def test_listar_processos_single_page(mocker):
    """Single page within the requested range — ``parse_datajud_api_response``
    returns 1 hit and the loop terminates after page 1 because
    ``current_page < end_page`` no longer holds."""
    mocker.patch("time.sleep")
    _add_page(
        "api_publica_tjsp",
        "listar_processos/single_page.json",
        numero_processo=CNJ_TJSP_CLEAN,
        tamanho_pagina=1000,
    )

    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP",
        numero_processo=CNJ_TJSP_FORMATTED,
        paginas=range(1, 2),
    )

    assert isinstance(df, pd.DataFrame)
    assert LISTAR_PROCESSOS_MIN_COLUMNS <= set(df.columns)
    assert len(df) == 1


@responses.activate
def test_listar_processos_no_results(mocker):
    """Empty ``hits.hits`` returns an empty DataFrame, not an error."""
    mocker.patch("time.sleep")
    _add_page(
        "api_publica_tjsp",
        "listar_processos/no_results.json",
        numero_processo="00000000000000000000",
        tamanho_pagina=1000,
    )

    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP",
        numero_processo="00000000000000000000",
        paginas=range(1, 2),
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_listar_processos_filtro_cnj_alias_inferido(mocker):
    """No ``tribunal=`` — alias is inferred from CNJ digits 13:16
    (id_justica + id_tribunal). Path unique to DataJud."""
    mocker.patch("time.sleep")
    _add_page(
        "api_publica_tjsp",
        "listar_processos/single_page.json",
        numero_processo=CNJ_TJSP_CLEAN,
        tamanho_pagina=1000,
    )

    df = jus.scraper("datajud").listar_processos(
        numero_processo=CNJ_TJSP_FORMATTED, paginas=range(1, 2)
    )

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    # The single POST must have hit api_publica_tjsp regardless of how the
    # alias was resolved.
    assert len(responses.calls) == 1
    assert "api_publica_tjsp" in responses.calls[0].request.url


@responses.activate
def test_listar_processos_filtro_tribunal_explicito_size_custom(mocker):
    """``tamanho_pagina=5`` lands in the body as ``size: 5``."""
    mocker.patch("time.sleep")
    _add_page(
        "api_publica_tjsp",
        "listar_processos/single_page.json",
        tamanho_pagina=5,
    )

    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP", paginas=range(1, 2), tamanho_pagina=5
    )

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1


@responses.activate
def test_listar_processos_mostrar_movs_true(mocker):
    """``mostrar_movs=True`` flips ``_source`` from ``{excludes: [...]}`` to
    ``True`` — DataJud-specific behaviour the matcher must catch."""
    mocker.patch("time.sleep")
    _add_page(
        "api_publica_tjsp",
        "listar_processos/single_page.json",
        mostrar_movs=True,
        tamanho_pagina=1000,
    )

    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP", paginas=range(1, 2), mostrar_movs=True
    )

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
