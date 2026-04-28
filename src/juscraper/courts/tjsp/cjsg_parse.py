"""Backwards-compat shim. Real cjsg parsing moved to
``juscraper.courts._esaj.parse`` (refs #84).

Re-exports the same public names the legacy unit tests import
(``tests/tjsp/test_cjsg_unit.py``).
"""
from .._esaj.parse import _parse_single_page as _cjsg_parse_single_page
from .._esaj.parse import cjsg_n_pags, cjsg_parse_manager

__all__ = ["_cjsg_parse_single_page", "cjsg_n_pags", "cjsg_parse_manager"]
