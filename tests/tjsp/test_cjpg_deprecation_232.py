"""Deprecacao dos plurais ``classes``/``assuntos``/``varas`` no cjpg TJSP (refs #232).

Garante que:

1. Plurais emitem :class:`DeprecationWarning` e seguem funcionando (1 release de
   convivencia minimo).
2. Plural + singular juntos -> :class:`ValueError` (uso conflitante; sem
   ``DeprecationWarning`` — o uso esta errado, nao apenas legado).
3. O body final do POST e identico independente do nome usado (singular vs
   plural-alias) e do tipo (int/str/list).
"""
from __future__ import annotations

import warnings

import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_tjsp_cjpg_params

BASE = "https://esaj.tjsp.jus.br/cjpg"


def _stub_no_results():
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", "cjpg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
    )


@responses.activate
def test_classes_plural_emite_deprecation_warning(tmp_path, mocker):
    mocker.patch("time.sleep")
    _stub_no_results()
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(DeprecationWarning, match=r"'classes' .* 'classe'"):
        df = scraper.cjpg("dano", paginas=1, classes=["12728"])
    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_assuntos_plural_emite_deprecation_warning(tmp_path, mocker):
    mocker.patch("time.sleep")
    _stub_no_results()
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(DeprecationWarning, match=r"'assuntos' .* 'assunto'"):
        df = scraper.cjpg("dano", paginas=1, assuntos=["3607"])
    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_varas_plural_emite_deprecation_warning(tmp_path, mocker):
    mocker.patch("time.sleep")
    _stub_no_results()
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(DeprecationWarning, match=r"'varas' .* 'vara'"):
        df = scraper.cjpg("dano", paginas=1, varas=["1-1-1"])
    assert isinstance(df, pd.DataFrame)


def test_classes_e_classe_juntos_levanta_value_error(tmp_path):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(ValueError, match=r"'classe' e 'classes' simultaneamente"):
        scraper.cjpg("dano", paginas=1, classe=12728, classes=["5885"])


def test_assuntos_e_assunto_juntos_levanta_value_error(tmp_path):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(ValueError, match=r"'assunto' e 'assuntos' simultaneamente"):
        scraper.cjpg("dano", paginas=1, assunto=3607, assuntos=["5885"])


def test_varas_e_vara_juntos_levanta_value_error(tmp_path):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(ValueError, match=r"'vara' e 'varas' simultaneamente"):
        scraper.cjpg("dano", paginas=1, vara="1-1-1", varas=["2-2-2"])


# --- Body parity: int / str / list / plural-alias geram o mesmo POST --------


def _expected_params(**overrides):
    base = make_tjsp_cjpg_params(
        pesquisa="dano moral",
        id_processo="",
        classes=["12728", "5885"],
        assuntos=None,
        varas=None,
        data_inicio="",
        data_fim="",
    )
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


@responses.activate
def test_body_parity_classe_lista_vs_csv_string(tmp_path, mocker):
    """``classe=[12728, 5885]`` deve produzir o mesmo POST que ``classe='12728,5885'``."""
    mocker.patch("time.sleep")
    expected = _expected_params()
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", "cjpg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(expected)],
    )
    jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "dano moral", paginas=1, classe=[12728, 5885]
    )


@responses.activate
def test_body_parity_classe_int_unico(tmp_path, mocker):
    """``classe=12728`` (int) deve produzir o mesmo POST que ``classe='12728'``."""
    mocker.patch("time.sleep")
    expected = _expected_params(**{"classeTreeSelection.values": "12728"})
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", "cjpg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(expected)],
    )
    jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "dano moral", paginas=1, classe=12728
    )


@responses.activate
def test_body_parity_plural_alias(tmp_path, mocker):
    """``classes=['12728','5885']`` deve produzir o mesmo POST que o singular."""
    mocker.patch("time.sleep")
    expected = _expected_params()
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", "cjpg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(expected)],
    )
    # Plurais ainda funcionam — so suprimo o DeprecationWarning aqui (testado
    # nos casos acima) para nao poluir o resultado.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
            "dano moral", paginas=1, classes=["12728", "5885"]
        )
