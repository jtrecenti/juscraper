"""Fixtures dos testes do TRF3."""
from __future__ import annotations

import pytest


@pytest.fixture
def tls_real():
    """Pedida pelo teste que precisa do adapter de TLS montado no raspador."""


@pytest.fixture(autouse=True)
def _sem_tls_navegador(monkeypatch, request):
    """Nos testes offline, o raspador não monta o adapter de TLS e o ``responses`` intercepta.

    O adapter sobrescreve ``HTTPAdapter.send``, que é onde o ``responses`` faz o
    mock. Testes ``integration`` e os que pedem ``tls_real`` usam o adapter real.
    """
    if request.node.get_closest_marker("integration") is not None or "tls_real" in request.fixturenames:
        return
    monkeypatch.setattr("juscraper.courts.trf3.client.montar_tls_navegador", lambda *_: None)
    monkeypatch.setattr("juscraper.courts.trf3.cjsg_download.montar_tls_navegador", lambda *_: None)
