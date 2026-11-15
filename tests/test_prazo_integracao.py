"""Testa o prazo por teste de integração definido em ``tests/conftest.py`` (#441).

Como em ``tests/test_anti_bot_marker.py``, a sessão ``pytester`` reusa o hook
real, re-exportado no conftest gerado.
"""
from __future__ import annotations

import pytest

_CONFTEST = "from tests.conftest import pytest_collection_modifyitems  # noqa: F401\n"

_TEST_MODULE = """
import pytest


@pytest.mark.integration
def test_ao_vivo():
    pass


@pytest.mark.integration
@pytest.mark.timeout(5)
def test_prazo_proprio():
    pass


def test_offline():
    pass
"""


@pytest.mark.parametrize(
    ("argumentos", "esperado"),
    [((), [(600,), (5,), None]), (("--timeout=7",), [None, (5,), None])],
    ids=["default", "timeout_na_linha_de_comando"],
)
def test_prazo_so_nos_testes_de_integracao(pytester, argumentos, esperado):
    """Só ``integration`` sem prazo próprio ganha o prazo; ``--timeout`` o substitui."""
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(_TEST_MODULE)

    # ``-p no:asyncio``: ver ``tests/test_anti_bot_marker.py``.
    items, _ = pytester.inline_genitems("-p", "no:asyncio", *argumentos)

    marcas = [item.get_closest_marker("timeout") for item in items]
    assert [marca.args if marca else None for marca in marcas] == esperado
