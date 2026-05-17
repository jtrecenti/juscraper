"""Filter-propagation contract for TJRR cjsg.

TJRR's ``cjsg`` exposes ``orgao_julgador`` (list of body codes),
``especie`` (list of decision-type codes), the date range
``data_julgamento_inicio/fim`` and ``relator`` (list of regimental
names resolved via lookup no form GET inicial — refs #158). Match
case-sensitive exato; nomes desconhecidos levantam ``ValueError``
listando os disponiveis.

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
from tests._helpers import assert_unknown_kwarg_raises, load_sample, urlencoded_body_subset_matcher
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


_RELATOR_ALMIRO_VALUE = (
    "br.jus.tjrr.bpu.domain.model.MagistradoBPU"
    "(matricula:3010559, nomeRegimental:ALMIRO PADILHA)"
)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_relator_lands_in_body(mocker):
    """``relator=[nomeRegimental]`` resolve para o bean opaco no body (refs #158).

    O scraper consulta ``relator_map`` (extraido do GET inicial em
    ``_collect_relator_map``) e injeta o value bean Java em
    ``menuinicial:relatorList``. Quem chama ``cjsg(relator=["ALMIRO PADILHA"])``
    nao precisa saber do bean.
    """
    mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial({"menuinicial:relatorList": _RELATOR_ALMIRO_VALUE})

    df = jus.scraper("tjrr").cjsg(
        "dano moral", paginas=1, relator=["ALMIRO PADILHA"],
    )
    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_relator_unknown_name_raises_value_error(mocker):
    """``relator`` com nome fora do form GET inicial dispara ``ValueError`` (refs #158).

    A mensagem cita o nome desconhecido e lista os nomes disponiveis —
    o usuario corrige sem precisar inspecionar o HTML manualmente.
    """
    mocker.patch("time.sleep")
    add_get_initial()

    with pytest.raises(ValueError, match="NOME INEXISTENTE"):
        jus.scraper("tjrr").cjsg(
            "dano moral", paginas=1, relator=["NOME INEXISTENTE"],
        )


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


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJRR` raise ``TypeError`` with
    the field name (refs #84, #93, #165, #183)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjrr").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjrr").cjsg_download,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


def test_cjsg_data_publicacao_kwarg_raises():
    """TJRR backend nao expoe filtro de data de publicacao;
    :class:`InputCJSGTJRR` so herda :class:`DataJulgamentoMixin`, entao
    ``data_publicacao_*`` deve cair como ``extra_forbidden`` -> ``TypeError``
    em vez de silently drop (refs #186)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjrr").cjsg,
        "data_publicacao_inicio",
        "dano moral",
        paginas=1,
    )
