"""Tests for query length validation in TJSP CJPG and CJSG downloads.

The TJSP search forms have a maxlength="120" attribute on the free-text
search field. Queries exceeding this limit cause platform errors, so we
validate early and raise QueryTooLongError.
"""
import pytest

from juscraper.courts.tjsp.cjpg_download import cjpg_download
from juscraper.courts.tjsp.exceptions import QueryTooLongError, validate_pesquisa_length


class TestCJPGQueryValidation:
    def test_query_too_long_raises_error(self):
        long_query = "a" * 121
        with pytest.raises(QueryTooLongError):
            cjpg_download(
                pesquisa=long_query,
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )

    def test_query_at_limit_passes_validation(self):
        query_120 = "a" * 120
        try:
            cjpg_download(
                pesquisa=query_120,
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )
        except QueryTooLongError:
            pytest.fail("120-char query must not raise QueryTooLongError")
        except Exception:
            pass  # Other failures expected (session=None, no network)

    def test_short_query_passes_validation(self):
        try:
            cjpg_download(
                pesquisa="direito do consumidor",
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )
        except QueryTooLongError:
            pytest.fail("Short query must not raise QueryTooLongError")
        except Exception:
            pass


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
