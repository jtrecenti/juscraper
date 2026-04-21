"""Offline contract tests for TJSP cjpg.

Mocks ``cjpg/pesquisar.do`` (GET for page 1) with the hand-crafted samples
kept from the unit-test suite. Validates the public DataFrame contract and
the query-string payload.

Sample strategy: the live eSAJ cjpg is currently returning "no results" for
anonymous queries regardless of search term, and the paginator itself
returns 500 on page 2 — see #108. Until #108 is resolved, the contract
reuses the synthetic samples kept for ``test_cjpg.py::TestCJPGUnit``:

- ``cjpg/results_legacy.html`` — 2 real processes, 25 total hits, "Mostrando …" wording.
- ``cjpg/results_novo_formato.html`` — current TJSP wording, "Resultados N a M de X".

Two gaps, each tracked by a separate issue:

- Multi-page coverage (``paginas=range(1, N)`` for ``N > 1``) — #108.
- Zero-result DataFrame path — #109 (cjpg_n_pags raises ValueError on the
  "Não foi encontrado nenhum resultado" page instead of returning an
  empty DataFrame).
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

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


@responses.activate
def test_cjpg_typical_legacy_format(tmp_path, mocker):
    """Typical query (legacy 'Mostrando N a M de X' wording) — DataFrame with schema.

    Multi-page coverage blocked by #108; exercises ``paginas=1`` only.
    """
    mocker.patch("time.sleep")
    _add_pesquisar("direito", "cjpg/results_legacy.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "direito", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert CJPG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


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


def test_cjpg_query_too_long_raises(tmp_path):
    """Pre-request guard: a pesquisa > 120 chars must raise before any HTTP."""
    pesquisa = "a" * 121
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(QueryTooLongError):
        scraper.cjpg(pesquisa, paginas=1)
