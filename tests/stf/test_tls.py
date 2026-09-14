"""Contexto TLS do STF nos dois caminhos de conexao do requests: direto e via proxy."""
import pytest

from juscraper.courts.stf._tls import _STFTLSAdapter

INTERMEDIARIA_CN = "GlobalSign GCC R6 AlphaSSL CA 2025"


def _nomes_comuns(ctx):
    return {
        valor
        for cert in ctx.get_ca_certs()
        for rdn in cert["subject"]
        for chave, valor in rdn
        if chave == "commonName"
    }


@pytest.mark.parametrize(
    "pool",
    [
        pytest.param(lambda adapter: adapter.poolmanager, id="direto"),
        pytest.param(lambda adapter: adapter.proxy_manager_for("http://proxy.example:3128"), id="proxy"),
    ],
)
def test_contexto_ssl_carrega_a_intermediaria(pool):
    ctx = pool(_STFTLSAdapter()).connection_pool_kw["ssl_context"]
    assert INTERMEDIARIA_CN in _nomes_comuns(ctx)
