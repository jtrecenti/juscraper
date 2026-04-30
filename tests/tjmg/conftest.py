"""Fixtures pytest compartilhadas pelos contratos cjsg do TJMG."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_txtcaptcha(mocker):
    """Patch ``txtcaptcha`` em ``sys.modules`` com stub estático.

    O ``import txtcaptcha`` lazy dentro de ``_solve_captcha`` resolve
    contra este fake; ``decrypt`` retorna sempre ``["12345"]``. Mantém
    a dependência fora de ``pyproject.toml`` (apenas o capture script
    real precisa do ``txtcaptcha`` instalado).
    """
    fake = MagicMock()
    fake.decrypt = MagicMock(return_value=["12345"])
    mocker.patch.dict(sys.modules, {"txtcaptcha": fake})
