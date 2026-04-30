"""Filter-propagation contract for TJRR cjsg.

TJRR's ``cjsg`` exposes ``orgao_julgador`` (list of body codes),
``especie`` (list of decision-type codes) and the date range
``data_julgamento_inicio/fim``. The ``relator`` parameter is accepted
for API parity but the live JSF form no longer carries it as a text
input (see ``_search`` in ``download.py``: ``relator`` is annotated
``# noqa: ARG001``); the dedicated ``test_cjsg_relator_lands_in_body``
xfails against this gap and tracks issue #158 (deprecation/remoção
planejada).

Aliases: ``query``/``termo`` (search term), ``data_inicio``/``data_fim``
(map to ``data_julgamento_*``).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample, urlencoded_body_subset_matcher
from tests.tjrr._helpers import INDEX_URL, add_get_initial, get_pesquisa_field_name

_SAMPLES_DIR = Path(__file__).parent / "samples" / "cjsg"
pytestmark = pytest.mark.skipif(
    not (_SAMPLES_DIR / "step_01_consulta.html").exists(),
    reason=(
        "TJRR samples ainda não capturados — rode "
        "`python -m tests.fixtures.capture.tjrr` para popular "
        "tests/tjrr/samples/cjsg/."
    ),
)


def _add_post_initial(expected_body_subset: dict[str, str]):
    """Empty-result POST whose body the matcher inspects."""
    responses.add(
        responses.POST,
        INDEX_URL,
        body=load_sample("tjrr", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[urlencoded_body_subset_matcher(expected_body_subset)],
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_all_filters_land_in_body(mocker):
    """Public filters (dates + lista orgao + lista especie) land in the body."""
    mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial({
        "menuinicial:datainicial_input": "01/01/2024",
        "menuinicial:datafinal_input": "31/03/2024",
        "menuinicial:tipoOrgaoList": "PRIMEIRA_TURMA_CIVEL",
        "menuinicial:tipoEspecieList": "ACORDAO",
    })

    df = jus.scraper("tjrr").cjsg(
        "dano moral",
        paginas=1,
        orgao_julgador=["PRIMEIRA_TURMA_CIVEL"],
        especie=["ACORDAO"],
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@pytest.mark.xfail(
    reason=(
        "TJRR: argumento `relator` é aceito pela API pública mas "
        "descartado silenciosamente pelo backend (campo virou "
        "select-multi de IDs). Refs #158 (deprecation/remoção planejada)."
    ),
    strict=True,
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_relator_lands_in_body(mocker):
    """``relator`` deveria propagar ao body — hoje não propaga (issue #158)."""
    mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial({"menuinicial:relator": "Fulano de Tal"})

    df = jus.scraper("tjrr").cjsg(
        "dano moral", paginas=1, relator="Fulano de Tal",
    )
    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """``query`` alias normalizes to ``pesquisa`` *e* propaga ao body."""
    mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial({get_pesquisa_field_name(): "dano moral"})

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjrr").cjsg(
            pesquisa=None, query="dano moral", paginas=1,
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """``termo`` alias normalizes to ``pesquisa`` *e* propaga ao body."""
    mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial({get_pesquisa_field_name(): "dano moral"})

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjrr").cjsg(
            pesquisa=None, termo="dano moral", paginas=1,
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` propagate as ``data_julgamento_*``."""
    mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial({
        "menuinicial:datainicial_input": "01/01/2024",
        "menuinicial:datafinal_input": "31/03/2024",
    })

    with pytest.warns(DeprecationWarning) as warnings_list:
        df = jus.scraper("tjrr").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="01/01/2024",
            data_fim="31/03/2024",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warnings_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
