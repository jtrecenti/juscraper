"""Filter-propagation contract for TJAP cjsg."""
from typing import Any

import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from tests._helpers import load_sample
from tests.tjap.test_cjsg_contract import BASE, _payload


@responses.activate
def test_cjsg_all_filters_land_in_json_body(mocker):
    """All TJAP public filters must reach the Tucujuris JSON payload."""
    mocker.patch("time.sleep")
    filters: dict[str, Any] = dict(
        orgao="tj",
        numero_processo="0000001-11.2024.8.03.0001",
        numero_acordao="12345",
        numero_ano="001858/1999",
        palavras_exatas=True,
        relator="FULANO DE TAL",
        secretaria="CAMARA UNICA",
        classe="APELACAO",
        votacao="Unanime",
        origem="MACAPA",
    )
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjap", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", **filters))],
    )

    df = jus.scraper("tjap").cjsg("dano moral", paginas=1, **filters)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_numero_cnj_alias_emits_deprecation_warning(mocker):
    """Deprecated ``numero_cnj`` maps to canonical ``numero_processo`` in the payload."""
    mocker.patch("time.sleep")
    numero = "0000001-11.2024.8.03.0001"
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjap", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", numero_processo=numero))],
    )

    with pytest.warns(DeprecationWarning, match="numero_cnj.*deprecado"):
        df = jus.scraper("tjap").cjsg(
            "dano moral",
            paginas=1,
            numero_cnj=numero,
        )

    assert isinstance(df, pd.DataFrame)
