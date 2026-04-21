"""Filter-propagation contract for TJAC cjsg (refs #84, #104 comment).

Confirms that every public parameter of ``scraper.cjsg(...)`` reaches the
POST body of ``cjsg/resultadoCompleta.do`` in the expected field. The
existing ``test_cjsg_contract.py`` only exercises the happy path with
empty filters; this file guards the refactor in #84 against silently
breaking filter propagation.
"""
import pandas as pd
import responses
from responses.matchers import query_param_matcher, urlencoded_params_matcher

import juscraper as jus
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_esaj_body

BASE = "https://esaj.tjac.jus.br/cjsg"

_ALL_FILTERS = dict(
    ementa="responsabilidade",
    numero_recurso="1000123-45.2023.8.26.0100",
    classe="cls-value",
    assunto="subj-value",
    comarca="comarca-value",
    orgao_julgador="og-value",
    data_julgamento_inicio="01/01/2024",
    data_julgamento_fim="31/03/2024",
    data_publicacao_inicio="01/02/2024",
    data_publicacao_fim="29/02/2024",
    origem="R",
    tipo_decisao="monocratica",
)


@responses.activate
def test_cjsg_all_filters_land_in_post_body(tmp_path, mocker):
    """Calling cjsg with every public filter produces a body matching
    ``make_esaj_body`` field-for-field. If the scraper drops any filter
    during the refactor, ``urlencoded_params_matcher`` rejects the POST
    and ``responses`` fails the assertion.
    """
    mocker.patch("time.sleep")
    expected_body = make_esaj_body(pesquisa="dano moral", **_ALL_FILTERS)
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjac", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(expected_body, allow_blank=True)],
    )
    # monocratica => tipoDeDecisao=D on the subsequent GET
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjac", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[query_param_matcher({"tipoDeDecisao": "D", "pagina": "1"})],
    )

    df = jus.scraper("tjac", download_path=str(tmp_path)).cjsg(
        "dano moral", paginas=1, **_ALL_FILTERS,
    )
    assert isinstance(df, pd.DataFrame)


def test_cjsg_unknown_kwarg_raises(tmp_path):
    """Kwargs that are not in InputCJSGEsajPuro must raise, not be silently ignored."""
    import pytest
    from pydantic import ValidationError
    scraper = jus.scraper("tjac", download_path=str(tmp_path))
    with pytest.raises((ValidationError, TypeError)):
        scraper.cjsg("dano moral", paginas=1, parametro_bobo="xyz")
