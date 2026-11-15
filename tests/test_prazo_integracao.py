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
def test_ao_vivo(request):
    marca = request.node.get_closest_marker("timeout")
    print("prazo", marca.args if marca else None)


@pytest.mark.integration
@pytest.mark.timeout(5)
def test_prazo_proprio(request):
    print("prazo", request.node.get_closest_marker("timeout").args)


def test_offline(request):
    print("prazo", request.node.get_closest_marker("timeout"))
"""

_INI = """
[pytest]
markers =
    integration: hits live external services
"""


@pytest.mark.parametrize(
    ("argumentos", "esperado"),
    [
        ((), ["prazo (600,)", "prazo (5,)", "prazo None"]),
        (("--timeout=7",), ["prazo None", "prazo (5,)", "prazo None"]),
    ],
    ids=["default", "timeout_na_linha_de_comando"],
)
def test_prazo_so_nos_testes_de_integracao(pytester, argumentos, esperado):
    """Só ``integration`` sem prazo próprio ganha o prazo; ``--timeout`` o substitui."""
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(_TEST_MODULE)
    pytester.makeini(_INI)

    # ``-p no:asyncio``: ver ``tests/test_anti_bot_marker.py``.
    resultado = pytester.runpytest("-p", "no:asyncio", "-s", *argumentos)

    resultado.assert_outcomes(passed=3)
    impressos = [linha[linha.index("prazo "):] for linha in resultado.outlines if "prazo " in linha]
    assert impressos == esperado
