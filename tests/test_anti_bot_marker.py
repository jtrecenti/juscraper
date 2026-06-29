"""Testa o hook ``anti_bot`` definido em ``tests/conftest.py`` (issue #292).

O hook (`pytest_runtest_makereport`) converte ``BotChallengeBlockedError`` em
xfail **apenas** para testes marcados ``anti_bot`` — o bloqueio Akamai dos TRFs
é falha ambiental (depende do IP), não regressão. Qualquer outra exceção, ou a
mesma exceção num teste sem o marker, continua falhando vermelho.

A cobertura exercita as **duas formas de aplicar o marker**: por decorator de
função (``@pytest.mark.anti_bot``) e por ``pytestmark`` de módulo — esta última
é a usada de verdade nos arquivos de integração dos TRFs. O hook resolve ambas
porque ``item.get_closest_marker`` percorre os nós-pai (incluindo o Module).

O teste roda uma sessão pytest isolada com a fixture ``pytester`` que **reusa o
hook real** (re-exportado no conftest gerado), em vez de duplicar a lógica:
assim o teste protege a implementação de verdade, não uma cópia.
"""
from __future__ import annotations

# Re-exporta o hook real para a sessão pytester. ``tests`` é importável como
# pacote (``pythonpath = ["tests"]`` + ``tests/__init__.py``).
_CONFTEST = "from tests.conftest import pytest_runtest_makereport  # noqa: F401\n"

_TEST_MODULE = '''
import pytest
from juscraper.core.exceptions import BotChallengeBlockedError


@pytest.mark.anti_bot
def test_block_becomes_xfail():
    raise BotChallengeBlockedError("TRF3", "https://pje1g.trf3.jus.br", reference="18.x")


@pytest.mark.anti_bot
def test_real_regression_still_fails():
    assert False, "parser quebrado — regressão real"


def test_block_without_marker_still_fails():
    raise BotChallengeBlockedError("TRF3", "https://pje1g.trf3.jus.br")
'''

# Espelha o uso real nos TRFs: o marker aplicado a nível de módulo via
# ``pytestmark`` (em vez de decorator por função). ``get_closest_marker``
# enxerga o marker pelo nó Module, então o bloqueio também vira xfail aqui.
_TEST_MODULE_PYTESTMARK = '''
import pytest
from juscraper.core.exceptions import BotChallengeBlockedError

pytestmark = pytest.mark.anti_bot


def test_module_level_block_becomes_xfail():
    raise BotChallengeBlockedError("TRF1", "https://pje1g.trf1.jus.br", reference="9.x")
'''

_INI = """
[pytest]
markers =
    anti_bot: anti-bot block becomes xfail
"""


def test_anti_bot_hook_distinguishes_block_from_regression(pytester):
    """Bloqueio+marker vira xfail; regressão real e bloqueio sem marker falham.

    Cobre o marker por decorator de função e por ``pytestmark`` de módulo (a
    forma usada nos TRFs): ambos os bloqueios viram xfail.
    """
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(
        test_func_marker=_TEST_MODULE,
        test_module_marker=_TEST_MODULE_PYTESTMARK,
    )
    pytester.makeini(_INI)

    # ``-p no:asyncio``: a sessão aninhada reconfigura todos os plugins do
    # processo; o pytest-asyncio emite um DeprecationWarning no ``configure``
    # que o ``filterwarnings = error`` da sessão externa transformaria em erro
    # fatal. O hook ``anti_bot`` não tem relação com asyncio — desligá-lo isola
    # o teste desse ruído de terceiros.
    result = pytester.runpytest("-p", "no:asyncio")

    # xfailed: bloqueio+marker-de-função e bloqueio+pytestmark-de-módulo.
    # failed: regressão real (AssertionError) e bloqueio sem marker.
    result.assert_outcomes(xfailed=2, failed=2)
