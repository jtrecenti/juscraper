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
from juscraper.courts.tjsp.client import TJSPScraper
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


# --- Regressao: plural alias + janela > 366d (auto_chunk) ------------------


def test_classes_plural_funciona_com_auto_chunk_long_window(tmp_path, mocker):
    """Regressao: plural alias + ``data_julgamento`` > 366d nao deve TypeError.

    Antes do fix de pop antes do ``run_auto_chunk``, a validacao upfront do
    schema :class:`InputCJPGTJSP` dentro do chunking via ``extra_forbidden``
    em ``classes`` (declarado so como alias deprecado, nao como campo do
    schema) — virava ``TypeError`` antes da pop acontecer em
    ``cjpg_download``. Agora o helper :func:`_pop_cjpg_plural_aliases` roda
    no entry point ``cjpg()`` antes do chunking.

    Mocka ``cjpg_download``/``cjpg_parse`` para isolar a pop+chunking do
    pipeline real (mesma estrategia de ``test_cjpg_auto_chunk_contract.py``).
    """
    mocker.patch.object(TJSPScraper, "cjpg_download", return_value="/fake/path")
    mocker.patch.object(
        TJSPScraper,
        "cjpg_parse",
        return_value=pd.DataFrame({"id_processo": ["x"]}),
    )
    mocker.patch("juscraper.courts.tjsp.client.shutil.rmtree")

    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(DeprecationWarning, match=r"'classes' .* 'classe'"):
        df = scraper.cjpg(
            "dano",
            classes=["12728"],
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
        )
    assert isinstance(df, pd.DataFrame)


def test_classes_plural_passa_canonico_para_cjpg_download(tmp_path, mocker):
    """Apos a pop em ``cjpg()``, ``cjpg_download`` recebe ``classe`` (singular).

    Garante que o helper substitui o alias antes da delegacao — sem isso,
    chamadas internas de chunking iriam re-popar o alias dentro de cada
    janela, duplicando o ``DeprecationWarning``.
    """
    download = mocker.patch.object(TJSPScraper, "cjpg_download", return_value="/fake/path")
    mocker.patch.object(
        TJSPScraper,
        "cjpg_parse",
        return_value=pd.DataFrame({"id_processo": ["x"]}),
    )
    mocker.patch("juscraper.courts.tjsp.client.shutil.rmtree")

    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        scraper.cjpg("dano", paginas=1, classes=["12728", "5885"])

    # cjpg_download deve receber 'classe' (canonico), nunca 'classes' (alias)
    assert download.call_count == 1
    call_kwargs = download.call_args.kwargs
    assert "classes" not in call_kwargs
    assert call_kwargs.get("classe") == ["12728", "5885"]


def test_classe_none_explicito_nao_conflita_com_classes_plural(tmp_path, mocker):
    """``classe=None`` explicito + ``classes=[...]`` nao deve levantar conflito.

    A checagem usa ``kwargs.get(_new) is not None`` (nao ``_new in kwargs``),
    entao passar ``classe=None`` explicito e tratado como "sem filtro
    canonico" e o alias plural prossegue normalmente. Alinha com a
    semantica de TJBA/DataJud.
    """
    mocker.patch.object(TJSPScraper, "cjpg_download", return_value="/fake/path")
    mocker.patch.object(
        TJSPScraper,
        "cjpg_parse",
        return_value=pd.DataFrame({"id_processo": ["x"]}),
    )
    mocker.patch("juscraper.courts.tjsp.client.shutil.rmtree")

    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(DeprecationWarning, match=r"'classes' .* 'classe'"):
        scraper.cjpg("dano", paginas=1, classe=None, classes=["12728"])
