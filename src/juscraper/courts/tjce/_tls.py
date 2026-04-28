"""TLS adapter for TJCE (SECLEVEL=1)."""
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context


class _TJCETLSAdapter(HTTPAdapter):
    """TJCE requires TLS SECLEVEL=1 due to its server configuration."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)
