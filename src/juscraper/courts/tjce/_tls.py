"""TLS adapter for TJCE (SECLEVEL=1)."""
import ssl

from urllib3.util.ssl_ import create_urllib3_context

from ...core.tls import ContextoTLSAdapter


def _contexto_ssl() -> ssl.SSLContext:
    ctx = create_urllib3_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return ctx


class _TJCETLSAdapter(ContextoTLSAdapter):
    """TJCE requires TLS SECLEVEL=1 due to its server configuration."""

    def contexto_ssl(self) -> ssl.SSLContext:
        """Contexto com ``SECLEVEL=1``."""
        return _contexto_ssl()
