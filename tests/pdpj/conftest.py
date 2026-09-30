"""Fixtures dos testes offline do PDPJ."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def esperas_do_backoff(request, mocker):
    """Registra as esperas do backoff do core sem dormir.

    Os perfis do PDPJ fazem até 6 tentativas com esperas de 2 a 32 s; um
    status retentável persistente num teste offline levaria 62 s. Os testes de
    integração mantêm o sono real, porque batem na API.
    """
    if request.node.get_closest_marker("integration"):
        return None
    return mocker.patch("juscraper.core.http.time.sleep")
