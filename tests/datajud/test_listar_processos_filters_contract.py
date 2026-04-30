"""Filters propagation for ``DatajudScraper.listar_processos`` (issue #140).

DataJud has no deprecated aliases (rule 6a of the contract checklist
in CLAUDE.md is N/A here): the API is recent and was designed with
the canonical names from day one.

The unknown-kwarg test asserts ``(ValidationError, TypeError)``: today
``listar_processos`` has a closed signature (no ``**kwargs``), so passing
an unknown keyword raises ``TypeError`` naturally. When
``InputListarProcessosDataJud`` is wired into the client (follow-up
PR — see ``CLAUDE.md`` "Schemas pydantic > Wiring segue o refactor #84"),
the same call will raise ``ValidationError`` instead. The tuple lets the
test continue to pass without modification across that transition.
"""
import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import header_matcher, json_params_matcher

import juscraper as jus
from juscraper.aggregators.datajud.client import DatajudScraper
from tests._helpers import load_sample
from tests.fixtures.capture.datajud import build_payload as _payload

BASE = DatajudScraper.BASE_API_URL
API_KEY = DatajudScraper.DEFAULT_API_KEY

CNJ_TJSP_FORMATTED = "1000413-22.2017.8.26.0415"
CNJ_TJSP_CLEAN = "10004132220178260415"


@responses.activate
def test_listar_processos_all_filters_land_in_body(mocker):
    """All filters propagate simultaneously: numero_processo + ano +
    classe + assuntos + mostrar_movs + tamanho_pagina. The matcher
    confirms the body has the four ``must_conditions`` in canonical order
    plus the dual ``dataAjuizamento`` range and ``_source: True``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        f"{BASE}/api_publica_tjsp/_search",
        body=load_sample("datajud", "listar_processos/single_page.json"),
        status=200,
        content_type="application/json",
        match=[
            json_params_matcher(_payload(
                numero_processo=CNJ_TJSP_CLEAN,
                ano_ajuizamento=2023,
                classe="436",
                assuntos=["1127", "1156"],
                mostrar_movs=True,
                tamanho_pagina=50,
            )),
            header_matcher(
                {"Authorization": f"APIKey {API_KEY}"}, strict_match=False
            ),
        ],
    )

    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP",
        numero_processo=CNJ_TJSP_FORMATTED,
        ano_ajuizamento=2023,
        classe="436",
        assuntos=["1127", "1156"],
        mostrar_movs=True,
        tamanho_pagina=50,
        paginas=range(1, 2),
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_listar_processos_cnj_invalido_nao_chama_api():
    """CNJ shorter than 20 digits fails ``clean_cnj`` length check; the
    client emits a ``UserWarning`` and returns an empty DataFrame
    *without* ever calling the API. With no ``responses.add`` registered,
    a hit on the API would surface as ``ConnectionError``."""
    with pytest.warns(UserWarning):
        df = jus.scraper("datajud").listar_processos(
            numero_processo="123-invalido"
        )

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert len(responses.calls) == 0


def test_listar_processos_unknown_kwarg_raises():
    """Unknown kwargs raise ``TypeError`` today (closed signature) and
    will raise ``ValidationError`` once the schema is wired. No HTTP
    mock needed — the error fires before any request is built."""
    with pytest.raises((ValidationError, TypeError)):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP", parametro_inventado="xyz"
        )


def test_listar_processos_tamanho_pagina_acima_do_cap():
    """``tamanho_pagina`` acima do cap documentado da API (10000) e
    rejeitado pelo schema antes da requisicao."""
    with pytest.raises(ValidationError):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP", tamanho_pagina=20000
        )


def test_listar_processos_tamanho_pagina_zero_ou_negativo():
    """``tamanho_pagina`` zero/negativo e rejeitado pelo schema
    (``ge=1``); o cursor ``search_after`` nao funciona com ``size=0``."""
    with pytest.raises(ValidationError):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP", tamanho_pagina=0
        )
    with pytest.raises(ValidationError):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP", tamanho_pagina=-100
        )
