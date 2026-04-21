"""Backwards-compat shim. Real cjsg download moved to
``juscraper.courts._esaj`` (refs #84).

Only the length-validation entry points remain so the legacy unit tests
(``tests/tjsp/test_query_validation.py``, ``tests/tjsp/test_search_limit.py``)
continue to pass unmodified.
"""
from __future__ import annotations

from .exceptions import QueryTooLongError, validate_pesquisa_length

__all__ = ["QueryTooLongError", "cjsg_download"]


def cjsg_download(pesquisa: str | None, *args, **kwargs):
    """Legacy entry point; raises ``QueryTooLongError`` for ``len(pesquisa) > 120``.

    The production path now goes through
    ``juscraper.scraper('tjsp').cjsg_download(...)`` via
    :class:`juscraper.courts._esaj.EsajSearchScraper`. This shim only
    enforces the 120-char guard so the pre-existing length tests keep
    their import path; other invocations raise ``NotImplementedError``.
    """
    validate_pesquisa_length(pesquisa, endpoint="CJSG")
    raise NotImplementedError(
        "juscraper.courts.tjsp.cjsg_download.cjsg_download is a compatibility "
        "shim since #84. Use juscraper.scraper('tjsp').cjsg_download(...) instead."
    )
