"""Wiring contract for TJRR cjsg.

Validates that ``cjsg`` rejects unknown kwargs via the pydantic pipeline
(``InputCJSGTJRR``, ``extra="forbid"``). Lives in a dedicated file so it
runs independently of the captured-samples skipif gate that protects the
filter-propagation contracts (refs #93, #147, #165).
"""
import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJRR` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjrr").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )
