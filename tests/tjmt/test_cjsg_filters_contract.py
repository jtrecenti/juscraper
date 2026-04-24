"""Filter-propagation contract for TJMT cjsg."""
import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests.tjmt.test_cjsg_contract import _add_config, _add_page


@responses.activate(registry=OrderedRegistry)
def test_cjsg_all_supported_filters_land_in_query_params(mocker):
    """Supported TJMT filters must reach the API query string."""
    mocker.patch("time.sleep")
    _add_config()
    _add_page(
        "dano moral",
        1,
        "cjsg/filters_all.json",
        quantidade_por_pagina=5,
        tipo_consulta="Acordao",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        relator="306",
        orgao_julgador="30",
        tipo_processo="942",
        thesaurus=True,
    )

    df = jus.scraper("tjmt").cjsg(
        "dano moral",
        paginas=1,
        quantidade_por_pagina=5,
        tipo_consulta="Acordao",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        relator="306",
        orgao_julgador="30",
        tipo_processo="942",
        thesaurus=True,
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_classe_filter_documents_current_not_implemented_behavior(mocker):
    """The public ``classe`` parameter is accepted but currently unsupported by the API helper."""
    mocker.patch("time.sleep")
    _add_config()
    with pytest.raises(NotImplementedError, match="classe"):
        jus.scraper("tjmt").cjsg("dano moral", paginas=1, classe="Apelacao")
