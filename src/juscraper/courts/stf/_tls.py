"""TLS adapter for the STF jurisprudence portal.

O servidor ``jurisprudencia.stf.jus.br`` envia o certificado folha sem a
intermediaria que o assina. Navegadores completam a cadeia sozinhos pelo campo
AIA do certificado; ``requests`` nao, e falha com ``CERTIFICATE_VERIFY_FAILED``.
O adapter acrescenta a intermediaria ao conjunto de CAs do certifi, sem desligar
a verificacao.

Quando o STF trocar de certificado, a conexao volta a falhar com o mesmo erro.
A correcao e substituir ``INTERMEDIARIA_PEM`` pela emissora nova, baixada da URL
"CA Issuers" do certificado servido (``openssl s_client -connect
jurisprudencia.stf.jus.br:443 -showcerts`` mostra o emissor).
"""
import certifi
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# GlobalSign GCC R6 AlphaSSL CA 2025, emitida por GlobalSign Root CA - R6
# (que ja esta no certifi). Valida ate 21/05/2027.
# SHA-256: A8:83:55:92:31:F8:38:8D:AF:35:CE:41:C8:10:10:40:AE:8F:D9:B6:56:43:42:47:B9:47:5A:F5:92:CC:08:CA
INTERMEDIARIA_PEM = """-----BEGIN CERTIFICATE-----
MIIFjTCCA3WgAwIBAgIRAIN9TriekS/nLK07x2kt3CAwDQYJKoZIhvcNAQELBQAw
TDEgMB4GA1UECxMXR2xvYmFsU2lnbiBSb290IENBIC0gUjYxEzARBgNVBAoTCkds
b2JhbFNpZ24xEzARBgNVBAMTCkdsb2JhbFNpZ24wHhcNMjUwNTIxMDIzNjUyWhcN
MjcwNTIxMDAwMDAwWjBVMQswCQYDVQQGEwJCRTEZMBcGA1UEChMQR2xvYmFsU2ln
biBudi1zYTErMCkGA1UEAxMiR2xvYmFsU2lnbiBHQ0MgUjYgQWxwaGFTU0wgQ0Eg
MjAyNTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAJ/oiu0Bviq52UUE
ADbFWmgu3rC7KDSMoorLN1Wd03McG3Z1aP71DlPCE33838r72Dfuj5M9LXfiQLJp
Au6MwNExmKOzothw4x0zGf5oBYyrCMGm3fBpLPafwYQ3MchBOWMTbf83rKUPLH48
KCJ0MnU8GUl8oA/J81wIvbbKPuNrFf6hvJDccjzc4NyxLz3A89zjV2g5whCg5O0u
9YX4Zxk9JHuc/LvllOJO4waAYLjbWBJkz3rV3ts1SmSYnJqmyRTIjXwQgRvhEYqt
DbRskt0W7M6cPwCze3GTBN2UHNpHkMs3YmVxku68I0aOQn5+uz//fDROP3z1Z/7I
APteRtECAwEAAaOCAV8wggFbMA4GA1UdDwEB/wQEAwIBhjAdBgNVHSUEFjAUBggr
BgEFBQcDAQYIKwYBBQUHAwIwEgYDVR0TAQH/BAgwBgEB/wIBADAdBgNVHQ4EFgQU
xbSTj28r3B5Iv7cQMIXO0bK7SC0wHwYDVR0jBBgwFoAUrmwFo5MT4qLn4tcc1sfw
f8hnU6AwewYIKwYBBQUHAQEEbzBtMC4GCCsGAQUFBzABhiJodHRwOi8vb2NzcDIu
Z2xvYmFsc2lnbi5jb20vcm9vdHI2MDsGCCsGAQUFBzAChi9odHRwOi8vc2VjdXJl
Lmdsb2JhbHNpZ24uY29tL2NhY2VydC9yb290LXI2LmNydDA2BgNVHR8ELzAtMCug
KaAnhiVodHRwOi8vY3JsLmdsb2JhbHNpZ24uY29tL3Jvb3QtcjYuY3JsMCEGA1Ud
IAQaMBgwCAYGZ4EMAQIBMAwGCisGAQQBoDIKAQMwDQYJKoZIhvcNAQELBQADggIB
AB/uvBuZf4CiuSahwiXn4geF52roAH+6jxsEPTXTfb7bbeMDXsYgRRsOTNA70ruZ
Tnz5DfFMuBhNoFhIFb0qR1izdy6VkdKOqFPNF2dOFI1EcnY9l2ory9mrzHqVbrL4
vzUd17FLUVyjTVU7PAv4nxyhnO1GTeT83YlrdRF31NyR6bvZVTEERHmpbWSgeveJ
LRtaMzlGWiLZ8IwkH7o6GH3jp/KPtDW4Npu8w64HrRZdN2pqQhi7+YKwfHM7H+2U
dM1BGN0sjOWMVbMSB9MtCsleS2Mb7TRZEbOHxECJLLIluQypZr7Pol3+hAqrhyKI
k+6y+Da0NeDuWxW59Ku4NvClqW1UFX1SpfNGhzVfp/CH+vPM1tySomx2jE0EnYZu
GwVucXPBsp5nUWqUV9+143glVuS7GTg9hFPjNBInn17HbCoIIQIOzj5Vd9bK3A9U
GxXNpwenDHEalCsD/4eQYDHPhFE7sNe0D/OXu+FAM02VZkARx37Jp4bDdujvgL9P
vZPR3wThvDN1CTU8Bc3xea3yKFAraKcPZLkhReQUAm2VpR+HSJRPlUpYizlF9WkL
h3KcAVCBJWvnOkVwxyU5QJMcnwW95JlOtx+9100GL99jHE5rs3gXp7F4bg8H01QT
9jVOhBBmQ7nQoXuwI0tqal2QUqZz3eeu62CU7xBwtfYR
-----END CERTIFICATE-----
"""


def _contexto_ssl():
    ctx = create_urllib3_context()
    ctx.load_verify_locations(cafile=certifi.where())
    ctx.load_verify_locations(cadata=INTERMEDIARIA_PEM)
    return ctx


class _STFTLSAdapter(HTTPAdapter):
    """Verifica o certificado do STF contra certifi + a intermediaria omitida pelo servidor.

    Com ``HTTPS_PROXY`` definido, o ``requests`` nao usa o pool de ``init_poolmanager``:
    monta um ``ProxyManager`` proprio em ``proxy_manager_for``. Sem o contexto tambem
    ali, a conexao via proxy volta ao bundle padrao e falha com ``CERTIFICATE_VERIFY_FAILED``.
    """

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = _contexto_ssl()
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        # O requests chama este metodo a cada requisicao e guarda o manager por proxy em
        # self.proxy_manager; so o primeiro uso de cada proxy precisa montar o contexto.
        if proxy not in self.proxy_manager:
            proxy_kwargs.setdefault("ssl_context", _contexto_ssl())
        return super().proxy_manager_for(proxy, **proxy_kwargs)
