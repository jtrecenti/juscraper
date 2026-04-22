"""Tests for query length validation in TJSP CJPG and CJSG downloads.

The TJSP search forms have a maxlength="120" attribute on the free-text
search field. Queries exceeding this limit cause platform errors, so we
validate early and raise QueryTooLongError.
"""
import pytest

import juscraper as jus
from juscraper.courts.tjsp.exceptions import QueryTooLongError, validate_pesquisa_length


class TestCJPGQueryValidation:
    """The public scraper entry point (``TJSPScraper.cjpg_download``) is the
    single validation boundary; the internal ``cjpg_download`` helper trusts
    its input (see :mod:`juscraper.courts.tjsp.cjpg_download`)."""

    def test_scraper_rejects_long_query(self, tmp_path):
        scraper = jus.scraper("tjsp", download_path=str(tmp_path))
        with pytest.raises(QueryTooLongError):
            scraper.cjpg_download(pesquisa="a" * 121, paginas=1)


class TestCJSGQueryValidation:
    def test_query_too_long_raises_error(self):
        long_query = "a" * 121
        with pytest.raises(QueryTooLongError):
            validate_pesquisa_length(long_query, endpoint="CJSG")

    def test_query_at_limit_passes_validation(self):
        validate_pesquisa_length("a" * 120, endpoint="CJSG")

    def test_short_query_passes_validation(self):
        validate_pesquisa_length("direito do consumidor", endpoint="CJSG")


class TestQueryValidationBoundary:
    def test_boundary_120_passes(self):
        validate_pesquisa_length("x" * 120, endpoint="CJPG")
        validate_pesquisa_length("x" * 120, endpoint="CJSG")

    def test_boundary_121_fails(self):
        with pytest.raises(QueryTooLongError):
            validate_pesquisa_length("x" * 121, endpoint="CJPG")
        with pytest.raises(QueryTooLongError):
            validate_pesquisa_length("x" * 121, endpoint="CJSG")

    def test_error_message_contains_length(self):
        with pytest.raises(QueryTooLongError, match="150 caracteres"):
            validate_pesquisa_length("a" * 150, endpoint="CJPG")

    def test_error_message_contains_limit(self):
        with pytest.raises(QueryTooLongError, match="120 caracteres"):
            validate_pesquisa_length("a" * 200, endpoint="CJSG")

    def test_query_too_long_is_value_error(self):
        assert issubclass(QueryTooLongError, ValueError)


class TestDeprecatedAliases:
    """Aliases deprecados (`query`/`termo`) devem emitir DeprecationWarning
    e ser popados antes do pydantic — caso contrario `extra='forbid'` acusa
    kwarg desconhecido e o `TypeError` amigavel esconde a intencao de
    retrocompat documentada no CLAUDE.md."""

    def test_cjsg_accepts_query_alias_with_warning(self, tmp_path):
        scraper = jus.scraper("tjsp", download_path=str(tmp_path))
        with pytest.warns(DeprecationWarning, match="query.*deprecado"):
            with pytest.raises(QueryTooLongError):
                scraper.cjsg_download(pesquisa=None, query="a" * 121, paginas=1)

    def test_cjpg_accepts_termo_alias_with_warning(self, tmp_path):
        scraper = jus.scraper("tjsp", download_path=str(tmp_path))
        with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
            with pytest.raises(QueryTooLongError):
                scraper.cjpg_download(termo="a" * 121, paginas=1)
