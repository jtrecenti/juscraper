"""Adaptador do ``requests`` com contexto TLS próprio, na conexão direta e via proxy."""
from __future__ import annotations

import ssl
from abc import ABC, abstractmethod
from typing import Any

from requests.adapters import HTTPAdapter
from urllib3 import PoolManager


class ContextoTLSAdapter(HTTPAdapter, ABC):
    """Base dos adaptadores que trocam o contexto TLS da conexão.

    A subclasse define :meth:`contexto_ssl`. O contexto vale nos dois caminhos
    do ``requests``: o pool de ``init_poolmanager``, da conexão direta, e o
    ``ProxyManager`` que ``proxy_manager_for`` monta quando há ``HTTPS_PROXY``.
    Sobrescrever só ``init_poolmanager`` deixa a conexão via proxy com o
    contexto padrão, e o handshake que o adaptador existe para consertar
    volta a falhar.
    """

    @abstractmethod
    def contexto_ssl(self) -> ssl.SSLContext:
        """Contexto TLS de um pool novo.

        O ``requests`` o pede dentro do ``__init__`` do adaptador e ao
        recriá-lo por ``pickle`` ou ``copy``, antes de qualquer atributo da
        instância existir: o contexto não pode depender deles.
        """

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        """Monta o pool da conexão direta com :meth:`contexto_ssl`."""
        kwargs["ssl_context"] = self.contexto_ssl()
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> PoolManager:
        """Monta o ``ProxyManager`` de ``proxy`` com :meth:`contexto_ssl`."""
        # O requests chama este método a cada requisição e guarda o manager por proxy em
        # self.proxy_manager; só o primeiro uso de cada proxy precisa montar o contexto.
        if proxy not in self.proxy_manager and "ssl_context" not in proxy_kwargs:
            proxy_kwargs["ssl_context"] = self.contexto_ssl()
        manager: PoolManager = super().proxy_manager_for(proxy, **proxy_kwargs)
        return manager
