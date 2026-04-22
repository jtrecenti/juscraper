"""Filter-propagation contract for TJSP cjsg (refs #84, #104 comment).

TJSP's body shape differs from the 5 eSAJ-puros: no ``conversationId``,
no ``dtPublicacao*``, ``origem`` derived from ``baixar_sg``. See
``make_tjsp_cjsg_body`` in ``tests/fixtures/capture/_util.py``.
"""
import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import query_param_matcher, urlencoded_params_matcher

import juscraper as jus
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_tjsp_cjsg_body

BASE = "https://esaj.tjsp.jus.br/cjsg"

_EMENTA = "responsabilidade"
_CLASSE = "cls-value"
_ASSUNTO = "subj-value"
_COMARCA = "comarca-value"
_ORGAO = "og-value"
_DATA_INI = "01/01/2024"
_DATA_FIM = "31/03/2024"
_BAIXAR_SG = False
_TIPO = "monocratica"


@responses.activate
def test_cjsg_all_filters_land_in_post_body(tmp_path, mocker):
    mocker.patch("time.sleep")
    # `make_tjsp_cjsg_body` mirrors ``build_tjsp_cjsg_body`` in production
    # code: maps ``baixar_sg=False`` -> ``origem="R"`` and
    # ``tipo_decisao="monocratica"`` -> ``tipoDecisaoSelecionados="D"``.
    expected_body = make_tjsp_cjsg_body(
        pesquisa="dano moral",
        ementa=_EMENTA,
        classe=_CLASSE,
        assunto=_ASSUNTO,
        comarca=_COMARCA,
        orgao_julgador=_ORGAO,
        data_inicio=_DATA_INI,
        data_fim=_DATA_FIM,
        baixar_sg=_BAIXAR_SG,
        tipo_decisao=_TIPO,
    )
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjsp", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(expected_body, allow_blank=True)],
    )
    # monocratica => tipoDeDecisao=D on GET
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjsp", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[query_param_matcher({"tipoDeDecisao": "D", "pagina": "1"})],
    )

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "dano moral",
        paginas=1,
        ementa=_EMENTA,
        classe=_CLASSE,
        assunto=_ASSUNTO,
        comarca=_COMARCA,
        orgao_julgador=_ORGAO,
        data_julgamento_inicio=_DATA_INI,
        data_julgamento_fim=_DATA_FIM,
        baixar_sg=_BAIXAR_SG,
        tipo_decisao=_TIPO,
    )
    assert isinstance(df, pd.DataFrame)


def test_cjsg_unknown_kwarg_raises(tmp_path):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises((ValidationError, TypeError)):
        scraper.cjsg("dano moral", paginas=1, parametro_bobo="xyz")


def test_cjsg_rejects_esaj_puro_only_fields(tmp_path):
    """TJSP doesn't expose ``numero_recurso``/``data_publicacao_*``/``origem``."""
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    for bad in ("numero_recurso", "data_publicacao_inicio", "origem"):
        with pytest.raises((ValidationError, TypeError)):
            scraper.cjsg("dano moral", paginas=1, **{bad: "x"})
