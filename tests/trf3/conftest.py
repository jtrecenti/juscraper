"""Fixtures dos testes do TRF3."""
from __future__ import annotations

import pytest
import requests

from juscraper.courts.trf3.transporte import TLSNavegadorAdapter


@pytest.fixture(autouse=True)
def _tls_navegador_pelo_mock(monkeypatch, request):
    """Nos testes offline, o adapter de TLS do TRF3 envia pelo ``HTTPAdapter`` do ``requests``.

    O ``responses`` intercepta ``HTTPAdapter.send``; o adapter, que sobrescreve
    ``send`` para usar o ``curl_cffi``, passaria por fora do mock. A busca de
    ``HTTPAdapter.send`` acontece na chamada, depois do patch do ``responses``.
    Testes ``integration`` usam o adapter real.
    """
    if request.node.get_closest_marker("integration") is not None:
        return

    def send(self, *args, **kwargs):
        return requests.adapters.HTTPAdapter.send(self, *args, **kwargs)

    monkeypatch.setattr(TLSNavegadorAdapter, "send", send)
