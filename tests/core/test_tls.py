"""``ContextoTLSAdapter``: o contexto da subclasse vale na conexão direta e via proxy."""
import ssl

import pytest
from urllib3.util.ssl_ import create_urllib3_context

from juscraper.core.tls import ContextoTLSAdapter

PROXY = "http://proxy.example:3128"


class _Adaptador(ContextoTLSAdapter):
    contextos: list[ssl.SSLContext]

    def contexto_ssl(self) -> ssl.SSLContext:
        self.contextos.append(create_urllib3_context())
        return self.contextos[-1]


@pytest.fixture(autouse=True)
def _sem_contextos(monkeypatch):
    monkeypatch.setattr(_Adaptador, "contextos", [], raising=False)


def test_contexto_vai_ao_pool_direto_e_ao_de_cada_proxy():
    adaptador = _Adaptador()

    direto = adaptador.poolmanager.connection_pool_kw["ssl_context"]
    via_proxy = adaptador.proxy_manager_for(PROXY).connection_pool_kw["ssl_context"]

    assert adaptador.contextos == [direto, via_proxy]
    # O requests pede o manager a cada requisição: o segundo pedido reaproveita manager e contexto.
    assert adaptador.proxy_manager_for(PROXY).connection_pool_kw["ssl_context"] is via_proxy
    assert len(adaptador.contextos) == 2


def test_base_sem_contexto_nao_e_montavel():
    with pytest.raises(TypeError, match="contexto_ssl"):
        ContextoTLSAdapter()  # type: ignore[abstract]
