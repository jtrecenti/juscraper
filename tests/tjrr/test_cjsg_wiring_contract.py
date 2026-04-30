"""Wiring contract for TJRR cjsg.

Validates that ``cjsg`` rejects unknown kwargs via the pydantic pipeline
(``InputCJSGTJRR``, ``extra="forbid"``). Lives in a dedicated file so it
runs independently of the captured-samples skipif gate that protects the
filter-propagation contracts (refs #93, #147, #165).
"""
import pytest

import juscraper as jus


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJRR` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        jus.scraper("tjrr").cjsg("dano moral", paginas=1, kwarg_inventado="x")
