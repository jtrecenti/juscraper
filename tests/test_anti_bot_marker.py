"""Testa o hook ``anti_bot`` definido em ``tests/conftest.py`` (issue #292).

O hook (`pytest_runtest_makereport`) converte ``BotChallengeBlockedError``, e o
``BloqueioAntiBotWarning`` que os métodos em lote emitem quando uma linha sai com
``bloqueio_anti_bot``, em
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
from juscraper.core.failures import avisar_falhas


@pytest.mark.anti_bot
def test_block_becomes_xfail():
    raise BotChallengeBlockedError("TRF3", "https://pje1g.trf3.jus.br", reference="18.x")


@pytest.mark.anti_bot
def test_real_regression_still_fails():
    assert False, "parser quebrado — regressão real"


def test_block_without_marker_still_fails():
    raise BotChallengeBlockedError("TRF3", "https://pje1g.trf3.jus.br")


@pytest.mark.anti_bot
def test_block_as_row_warning_becomes_xfail():
    # cpopg em lote: o bloqueio vira linha e aviso, promovido a erro. O
    # bloqueio é a 4ª falha, fora dos exemplos que a mensagem cita.
    falhas = [f"processo {i}: http_500" for i in range(3)] + ["processo 3: bloqueio_anti_bot"]
    avisar_falhas(falhas, "TRF3Scraper.cpopg", "consulta(s) de processo")


@pytest.mark.anti_bot
def test_other_row_warning_still_fails():
    avisar_falhas(["processo 1: http_500"], "TRF3Scraper.cpopg", "consulta(s) de processo")
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
filterwarnings = error
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

    # xfailed: bloqueio+marker-de-função, bloqueio+pytestmark-de-módulo e o
    # aviso de linha com bloqueio_anti_bot.
    # failed: regressão real (AssertionError), bloqueio sem marker e aviso de
    # linha com outro motivo.
    result.assert_outcomes(xfailed=3, failed=3)
