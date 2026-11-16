"""TLS adapter for TJCE (SECLEVEL=1)."""
from typing import Any

from requests.adapters import HTTPAdapter
from urllib3 import PoolManager
from urllib3.util.ssl_ import create_urllib3_context


def _contexto_ssl():
    ctx = create_urllib3_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return ctx


class _TJCETLSAdapter(HTTPAdapter):
    """TJCE requires TLS SECLEVEL=1 due to its server configuration.

    Com ``HTTPS_PROXY`` definido, o ``requests`` não usa o pool de ``init_poolmanager``:
    monta um ``ProxyManager`` próprio em ``proxy_manager_for``. Sem o contexto também
    ali, a conexão via proxy volta ao nível de segurança padrão e o handshake falha.
    """

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = _contexto_ssl()
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> PoolManager:
        # O requests chama este método a cada requisição e guarda o manager por proxy em
        # self.proxy_manager; só o primeiro uso de cada proxy precisa montar o contexto.
        if proxy not in self.proxy_manager:
            proxy_kwargs.setdefault("ssl_context", _contexto_ssl())
        manager: PoolManager = super().proxy_manager_for(proxy, **proxy_kwargs)
        return manager
