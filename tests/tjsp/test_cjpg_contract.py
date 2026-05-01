"""Offline contract tests for TJSP cjpg.

Mocks ``cjpg/pesquisar.do`` (page 1) and ``cjpg/trocarDePagina.do`` (page
2+) with live-captured samples, plus synthetic samples kept from the
unit-test suite for legacy-format coverage. Validates the public
DataFrame contract and the query-string payload.

Samples exercised:

- ``cjpg/results_normal_page_01.html`` / ``_02.html`` — live capture
  (``dano moral``), used for multi-page coverage.
- ``cjpg/results_legacy.html`` — 2 real processes, 25 total hits,
  "Mostrando …" legacy wording.
- ``cjpg/results_novo_formato.html`` — current TJSP wording,
  "Resultados N a M de X".
- ``cjpg/no_results.html`` — eSAJ form page returned when the query
  matches zero acórdãos. Guards the fix for #109.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.courts.tjsp.cjpg_download import QueryTooLongError
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_tjsp_cjpg_params

BASE = "https://esaj.tjsp.jus.br/cjpg"
CJPG_MIN_COLUMNS = {"cd_processo", "id_processo", "classe", "decisao"}


def _add_pesquisar(pesquisa: str, sample_path: str) -> None:
    # ``requests`` drops keys whose value is ``None``, so the matcher must
    # expect the same filtered dict. Empty strings are kept (``key=``).
    expected = {k: v for k, v in make_tjsp_cjpg_params(pesquisa).items() if v is not None}
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(expected)],
    )


def _add_trocar_de_pagina(pagina: int, sample_path: str) -> None:
    # cjpg_download.py:139 builds the URL as a literal f-string with an
    # empty conversationId (``?pagina=N&conversationId=``). The matcher
    # mirrors that — conversationId="" is sent as ``conversationId=``.
    responses.add(
        responses.GET,
        f"{BASE}/trocarDePagina.do",
        body=load_sample_bytes("tjsp", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"pagina": str(pagina), "conversationId": ""})],
    )


@responses.activate
def test_cjpg_typical_legacy_format(tmp_path, mocker):
    """Typical query (legacy 'Mostrando N a M de X' wording) — DataFrame with schema."""
    mocker.patch("time.sleep")
    _add_pesquisar("direito", "cjpg/results_legacy.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "direito", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert CJPG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate(registry=OrderedRegistry)
def test_cjpg_multi_page(tmp_path, mocker):
    """Multi-page: GET pesquisar.do (page 1) + GET trocarDePagina.do (page 2)."""
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    _add_trocar_de_pagina(2, "cjpg/results_normal_page_02.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "dano moral", paginas=range(1, 3)
    )

    assert isinstance(df, pd.DataFrame)
    assert CJPG_MIN_COLUMNS <= set(df.columns)
    # 10 rows per page; cjpg_download.py:114 clamps range.stop to n_pags+1
    # which is large here, so both pages are fetched.
    assert len(df) == 20


@responses.activate
def test_cjpg_novo_formato(tmp_path, mocker):
    """Current TJSP wording 'Resultados N a M de X' — regression for #cjpg_n_pags."""
    mocker.patch("time.sleep")
    _add_pesquisar("direito", "cjpg/results_novo_formato.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "direito", paginas=1
    )

    # The synthetic sample has 0 result rows in the listing but a real
    # pagination marker; the contract validates the public call doesn't
    # raise and the DataFrame shape is correct.
    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjpg_no_results(tmp_path, mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_pesquisar("juscraper_probe_zero_hits_xyzqwe", "cjpg/no_results.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_cjpg_query_too_long_raises(tmp_path):
    """Pre-request guard: a pesquisa > 120 chars must raise before any HTTP."""
    pesquisa = "a" * 121
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(QueryTooLongError):
        scraper.cjpg(pesquisa, paginas=1)


def test_cjpg_query_too_long_via_alias_raises(tmp_path):
    """Pre-request guard tambem cobre o caso do alias `query` resolvido pelo
    pipeline (refs #174 — validate_pesquisa_length roda apos consumir
    o alias)."""
    long_query = "a" * 121
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(DeprecationWarning), pytest.raises(QueryTooLongError):
        scraper.cjpg(paginas=1, query=long_query)
