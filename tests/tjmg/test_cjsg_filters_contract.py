"""Filter-propagation contract for TJMG cjsg.

TJMG's ``cjsg`` accepts ``pesquisar_por`` (``"ementa"`` | ``"acordao"``),
``order_by`` (``0``/``1``/``2``), ``linhas_por_pagina``, and the two
date ranges (``data_julgamento_inicio/fim``,
``data_publicacao_inicio/fim``). These ride into the GET on
``pesquisaPalavrasEspelhoAcordao.do`` as query params.

Aliases: ``query``/``termo`` (search term) and ``data_inicio``/``data_fim``
(map to ``data_julgamento_*`` with a ``DeprecationWarning``).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample_bytes, query_param_subset_matcher
from tests.tjmg._helpers import SEARCH_URL, add_captcha, add_dwr, add_form

_SAMPLES_DIR = Path(__file__).parent / "samples" / "cjsg"
pytestmark = pytest.mark.skipif(
    not (_SAMPLES_DIR / "form_acordao.html").exists(),
    reason=(
        "TJMG samples ainda não capturados — rode "
        "`pip install txtcaptcha && python -m tests.fixtures.capture.tjmg` "
        "para popular tests/tjmg/samples/cjsg/."
    ),
)


def _add_search(expected_query_subset: dict[str, str]):
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=load_sample_bytes("tjmg", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=ISO-8859-1",
        match=[query_param_subset_matcher(expected_query_subset)],
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_all_filters_land_in_request(mock_txtcaptcha, mocker):
    """All public filters propagate to the query string of the search GET."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search({
        "palavras": "dano moral",
        "numeroRegistro": "1",
        "pesquisarPor": "acordao",
        "orderByData": "1",
        "linhasPorPagina": "20",
        "dataJulgamentoInicial": "01/01/2024",
        "dataJulgamentoFinal": "31/03/2024",
        "dataPublicacaoInicial": "02/01/2024",
        "dataPublicacaoFinal": "01/04/2024",
    })

    df = jus.scraper("tjmg").cjsg(
        "dano moral",
        paginas=1,
        pesquisar_por="acordao",
        order_by=1,
        linhas_por_pagina=20,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        data_publicacao_inicio="02/01/2024",
        data_publicacao_fim="01/04/2024",
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_query_alias_emits_deprecation_warning(mock_txtcaptcha, mocker):
    """``query`` alias normalizes to ``pesquisa`` with a warning."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search({"palavras": "dano moral", "numeroRegistro": "1"})

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjmg").cjsg(
            pesquisa=None, query="dano moral", paginas=1,
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_termo_alias_emits_deprecation_warning(mock_txtcaptcha, mocker):
    """``termo`` alias normalizes to ``pesquisa`` with a warning."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search({"palavras": "dano moral", "numeroRegistro": "1"})

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjmg").cjsg(
            pesquisa=None, termo="dano moral", paginas=1,
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mock_txtcaptcha, mocker):
    """``data_inicio``/``data_fim`` propagate as ``data_julgamento_*``."""
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    _add_search({
        "palavras": "dano moral",
        "numeroRegistro": "1",
        "dataJulgamentoInicial": "01/01/2024",
        "dataJulgamentoFinal": "31/03/2024",
    })

    with pytest.warns(DeprecationWarning) as warnings_list:
        df = jus.scraper("tjmg").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="01/01/2024",
            data_fim="31/03/2024",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warnings_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
