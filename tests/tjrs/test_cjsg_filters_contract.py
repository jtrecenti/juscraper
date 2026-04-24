"""Filter-propagation contract for TJRS cjsg."""
import pandas as pd
import responses

import juscraper as jus
from tests.tjrs.test_cjsg_contract import _add_page


@responses.activate
def test_cjsg_all_filters_land_in_form_body(mocker):
    """All TJRS public filters must reach the nested Solr params form body."""
    mocker.patch("time.sleep")
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        classe="Apelacao",
        assunto="Dano moral",
        orgao_julgador="Primeira Camara",
        relator="FULANO DE TAL",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
        tipo_processo="Civel",
        secao="crime",
    )

    df = jus.scraper("tjrs").cjsg(
        "dano moral",
        paginas=1,
        classe="Apelacao",
        assunto="Dano moral",
        orgao_julgador="Primeira Camara",
        relator="FULANO DE TAL",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
        tipo_processo="Civel",
        secao="crime",
    )

    assert isinstance(df, pd.DataFrame)
