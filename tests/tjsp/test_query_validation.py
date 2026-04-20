"""
Tests for query length validation in TJSP CJPG and CJSG downloads.

The TJSP search forms have a maxlength="120" attribute on the free-text
search field. Queries exceeding this limit cause platform errors, so we
validate early and raise QueryTooLongError.
"""
import pytest

from juscraper.courts.tjsp.cjpg_download import QueryTooLongError as CJPGQueryTooLongError
from juscraper.courts.tjsp.cjpg_download import cjpg_download
from juscraper.courts.tjsp.cjsg_download import QueryTooLongError as CJSGQueryTooLongError
from juscraper.courts.tjsp.cjsg_download import cjsg_download

# ---------------------------------------------------------------------------
# CJPG
# ---------------------------------------------------------------------------


class TestCJPGQueryValidation:
    """Tests for query length validation in cjpg_download."""

    def test_query_too_long_raises_error(self):
        """Query exceeding 120 characters should raise QueryTooLongError."""
        long_query = "a" * 121
        with pytest.raises(CJPGQueryTooLongError):
            cjpg_download(
                pesquisa=long_query,
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )

    def test_query_at_limit_passes_validation(self):
        """Query with exactly 120 characters should NOT raise QueryTooLongError."""
        query_120 = "a" * 120
        try:
            cjpg_download(
                pesquisa=query_120,
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )
        except CJPGQueryTooLongError:
            pytest.fail("120-char query must not raise QueryTooLongError")
        except Exception:
            pass  # Other failures are expected (session=None, no network)

    def test_short_query_passes_validation(self):
        """Short query should NOT raise QueryTooLongError."""
        try:
            cjpg_download(
                pesquisa="direito do consumidor",
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )
        except CJPGQueryTooLongError:
            pytest.fail("Short query must not raise QueryTooLongError")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CJSG
# ---------------------------------------------------------------------------

class TestCJSGQueryValidation:
    """Tests for query length validation in cjsg_download."""

    def test_query_too_long_raises_error(self):
        """Query exceeding 120 characters should raise QueryTooLongError."""
        long_query = "a" * 121
        with pytest.raises(CJSGQueryTooLongError):
            cjsg_download(
                pesquisa=long_query,
                download_path="/tmp/test",
                u_base="https://esaj.tjsp.jus.br/",
                get_n_pags_callback=lambda _html: 1,
            )

    def test_query_at_limit_passes_validation(self):
        """Query with exactly 120 characters should NOT raise QueryTooLongError."""
        query_120 = "a" * 120
        try:
            cjsg_download(
                pesquisa=query_120,
                download_path="/tmp/test",
                u_base="https://esaj.tjsp.jus.br/",
                get_n_pags_callback=lambda x: 1,
            )
        except CJSGQueryTooLongError:
            pytest.fail("120-char query must not raise QueryTooLongError")
        except Exception:
            pass  # Other failures are expected (network, etc.)

    def test_short_query_passes_validation(self):
        """Short query should NOT raise QueryTooLongError."""
        try:
            cjsg_download(
                pesquisa="direito do consumidor",
                download_path="/tmp/test",
                u_base="https://esaj.tjsp.jus.br/",
                get_n_pags_callback=lambda x: 1,
            )
        except CJSGQueryTooLongError:
            pytest.fail("Short query must not raise QueryTooLongError")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Boundary and error message
# ---------------------------------------------------------------------------

class TestQueryValidationBoundary:
    """Boundary and error message tests."""

    def test_boundary_120_passes(self):
        """Exactly 120 chars should NOT raise QueryTooLongError."""
        query = "x" * 120
        try:
            cjpg_download(
                pesquisa=query,
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )
        except CJPGQueryTooLongError:
            pytest.fail("120-char query must not raise QueryTooLongError")
        except Exception:
            pass  # session=None triggers other error downstream

    def test_boundary_121_fails(self):
        """121 chars should raise QueryTooLongError."""
        query = "x" * 121
        with pytest.raises(CJPGQueryTooLongError):
            cjpg_download(
                pesquisa=query,
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )

    def test_error_message_contains_length(self):
        """Error message should contain the current query length."""
        query = "a" * 150
        with pytest.raises(CJPGQueryTooLongError, match="150 caracteres"):
            cjpg_download(
                pesquisa=query,
                session=None,  # type: ignore[arg-type]
                u_base="https://esaj.tjsp.jus.br/",
                download_path="/tmp/test",
            )

    def test_error_message_contains_limit(self):
        """Error message should mention the 120 character limit."""
        query = "a" * 200
        with pytest.raises(CJSGQueryTooLongError, match="120 caracteres"):
            cjsg_download(
                pesquisa=query,
                download_path="/tmp/test",
                u_base="https://esaj.tjsp.jus.br/",
                get_n_pags_callback=lambda _html: 1,
            )

    def test_query_too_long_is_value_error(self):
        """Verify that QueryTooLongError is a subclass of ValueError."""
        assert issubclass(CJPGQueryTooLongError, ValueError)
        assert issubclass(CJSGQueryTooLongError, ValueError)
