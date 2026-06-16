"""Shared pytest fixtures for juscraper tests.

Test-level helpers live in ``tests/helpers.py`` so they can be imported by
per-tribunal test files (pytest does not import ``conftest.py`` as a regular
module). Fixtures are kept here so pytest picks them up automatically.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from juscraper.core.exceptions import BotChallengeBlockedError
from tests.helpers import DATA_ALVO_BR, DATA_ALVO_FIM_BR, DATA_ALVO_FIM_ISO, DATA_ALVO_ISO

# Habilita a fixture ``pytester`` (sessões pytest isoladas) usada por
# ``tests/test_anti_bot_marker.py`` para exercitar o hook ``anti_bot`` abaixo.
pytest_plugins = ["pytester"]


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Converte um bloqueio anti-bot em xfail para testes marcados ``anti_bot``.

    Portais protegidos por Akamai (TRF1/TRF3/TRF5 ``cpopg``) devolvem HTTP 403
    ``Access Denied`` a partir de IPs de datacenter/CI; o código levanta
    ``BotChallengeBlockedError`` de propósito (bloqueio session-wide). Isso é
    falha *ambiental* — depende do IP do cliente, não é regressão —, então vira
    xfail em vez de vermelho. Qualquer outra exceção continua falhando
    normalmente, preservando o sinal de regressão real (parser quebrado, schema
    rejeitando input antes válido, coluna renomeada). De IP residencial, sem
    bloqueio, o teste passa de forma limpa. Ver issue #292.
    """
    report = yield
    if (
        report.when == "call"
        and call.excinfo is not None
        and item.get_closest_marker("anti_bot") is not None
        and call.excinfo.errisinstance(BotChallengeBlockedError)
    ):
        report.outcome = "skipped"
        report.wasxfail = "bloqueio anti-bot (Akamai) — falha ambiental, não regressão"
    return report


@pytest.fixture
def tests_dir() -> Path:
    """Path to ``tests/``. Compose with ``tribunal`` and ``samples`` to reach fixtures.

    Most tests should prefer ``tests._helpers.load_sample`` instead.
    """
    return Path(__file__).parent


@pytest.fixture
def data_alvo_br() -> str:
    """Start of the reference work week in Brazilian format (DD/MM/YYYY)."""
    return DATA_ALVO_BR


@pytest.fixture
def data_alvo_fim_br() -> str:
    """End of the reference work week in Brazilian format (DD/MM/YYYY)."""
    return DATA_ALVO_FIM_BR


@pytest.fixture
def data_alvo_iso() -> str:
    """Start of the reference work week in ISO format (YYYY-MM-DD)."""
    return DATA_ALVO_ISO


@pytest.fixture
def data_alvo_fim_iso() -> str:
    """End of the reference work week in ISO format (YYYY-MM-DD)."""
    return DATA_ALVO_FIM_ISO
