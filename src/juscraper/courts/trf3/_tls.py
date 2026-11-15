"""Transporte com TLS de navegador para a consulta pública do PJe do TRF3.

O Akamai na frente de ``pje1g-consultapublica`` e ``pje2g-consultapublica``
filtra pela impressão digital TLS/HTTP2 do cliente: uma requisição do
``requests`` fica sem resposta até o timeout, inclusive de IP residencial,
enquanto a mesma requisição feita com a impressão digital do Chrome responde
(diagnóstico no PR #398). :class:`TLSNavegadorAdapter` é um adapter do
``requests`` que entrega a requisição ao ``curl_cffi`` imitando o Chrome. A
sessão do raspador continua sendo uma ``requests.Session``, e o retry e os
motivos de falha de :class:`~juscraper.core.http.HTTPScraper` não mudam.

O ``curl_cffi`` é o extra opcional ``juscraper[tls]``. Ele só é importado na
primeira requisição: sem o extra, o raspador é criado, e a primeira consulta
do ``cpopg``/``cposg`` levanta ``ImportError`` com a instrução de instalação.
O ``cjsg`` usa o adapter quando o extra está instalado
(:func:`tls_navegador_disponivel`) e, sem ele, segue com o ``requests``, que o
portal de jurisprudência atende de IP residencial, mas não de IP de
datacenter.
"""
from __future__ import annotations

import importlib
import io
from types import ModuleType
from typing import TYPE_CHECKING

import requests
from requests.adapters import HTTPAdapter
from urllib3 import HTTPHeaderDict, HTTPResponse

if TYPE_CHECKING:
    from curl_cffi.requests import Response as CurlResponse
    from curl_cffi.requests import Session as CurlSession

#: Navegador cuja impressão digital TLS/HTTP2 o ``curl_cffi`` reproduz.
IMPERSONATE = "chrome"

# Cabeçalhos que o ``curl_cffi`` controla: repassar os do ``requests`` mudaria a
# impressão digital (``Connection`` não existe em HTTP/2) ou desligaria a
# descompressão automática do corpo.
_CABECALHOS_DO_CURL = frozenset({"connection", "accept-encoding", "content-length", "host"})

MENSAGEM_SEM_EXTRA = (
    "A consulta processual do TRF3 (cpopg e cposg) precisa do curl_cffi: o Akamai do portal "
    "não responde a clientes sem TLS de navegador. Instale com `pip install 'juscraper[tls]'`."
)


class TLSNavegadorAdapter(HTTPAdapter):
    """Adapter do ``requests`` que faz a requisição pelo ``curl_cffi`` com TLS do Chrome.

    Os cookies ficam na sessão do ``curl_cffi``, que vive enquanto o adapter
    estiver montado, e não aparecem em ``session.cookies``. Erros de transporte
    do ``curl_cffi`` viram as exceções equivalentes do ``requests``, que a
    política de retry já trata; erros de configuração (URL inválida, navegador
    a imitar desconhecido) sobem como vieram. ``stream`` e ``cert`` são
    ignorados.

    O ``timeout`` ``(conexão, leitura)`` não tem o mesmo sentido do
    ``requests``: no ``curl_cffi``, a soma dos dois limita a transferência
    inteira, e não o intervalo entre leituras. Uma peça grande que demore mais
    que essa soma sai ``timeout``; ``politica={"documento": {"timeout": ...}}``
    aumenta o limite.
    """

    def __init__(self) -> None:
        """Cria o adapter sem importar o ``curl_cffi``; a sessão nasce na primeira requisição."""
        super().__init__()
        self._sessao_curl: CurlSession | None = None

    def send(self, request: requests.PreparedRequest, *_args: object, **kwargs: object) -> requests.Response:
        """Envia ``request`` pelo ``curl_cffi``.

        ``requests.Session`` chama ``send`` com ``stream``, ``timeout``,
        ``verify``, ``cert`` e ``proxies`` por nome; só ``timeout``, ``verify``
        e ``proxies`` seguem para o ``curl_cffi``.

        Raises:
            ImportError: Quando o ``curl_cffi`` (extra ``juscraper[tls]``) não está instalado.
            requests.ConnectTimeout: Timeout ao conectar.
            requests.ReadTimeout: A transferência passou do ``timeout``.
            requests.ConnectionError: Outro erro de transporte (conexão, proxy,
                stream HTTP/2 reiniciado, corpo incompleto).
        """
        curl = _importar_curl_cffi()
        if self._sessao_curl is None:
            self._sessao_curl = curl.Session(impersonate=IMPERSONATE)
        proxies = kwargs.get("proxies")
        try:
            resposta = self._sessao_curl.request(
                request.method or "GET",
                request.url or "",
                headers={k: v for k, v in request.headers.items() if k.lower() not in _CABECALHOS_DO_CURL},
                data=request.body,
                timeout=kwargs.get("timeout"),
                verify=kwargs.get("verify", True),
                proxies=proxies if isinstance(proxies, dict) and proxies else None,
                allow_redirects=False,
            )
        except curl.exceptions.ConnectTimeout as exc:
            raise requests.ConnectTimeout(str(exc), request=request) from exc
        except curl.exceptions.Timeout as exc:
            raise requests.ReadTimeout(str(exc), request=request) from exc
        except (
            curl.exceptions.ConnectionError,
            curl.exceptions.ProxyError,
            # No curl_cffi, HTTPError é transporte (stream HTTP/2 reiniciado, corpo incompleto), não status.
            curl.exceptions.HTTPError,
            curl.exceptions.ChunkedEncodingError,
        ) as exc:
            raise requests.ConnectionError(str(exc), request=request) from exc
        except curl.exceptions.RequestException as exc:
            # Código do curl sem classe própria chega como RequestException puro; as
            # subclasses restantes são de configuração (URL inválida, impersonate) e sobem.
            if exc.__class__ is not curl.exceptions.RequestException:
                raise
            raise requests.ConnectionError(str(exc), request=request) from exc
        return self.build_response(request, _como_urllib3(resposta))

    def close(self) -> None:
        """Fecha a sessão do ``curl_cffi``, se ela chegou a ser criada."""
        if self._sessao_curl is not None:
            self._sessao_curl.close()
            self._sessao_curl = None
        super().close()


def _como_urllib3(resposta: CurlResponse) -> HTTPResponse:
    """A resposta do ``curl_cffi`` como a ``HTTPResponse`` que ``HTTPAdapter.build_response`` consome.

    O ``curl_cffi`` já descomprimiu o corpo: sem ``Content-Encoding``, o
    ``urllib3`` não tenta descomprimir de novo, e sem ``Content-Length``, que
    mede o corpo comprimido, não acusa leitura incompleta.
    """
    cabecalhos = HTTPHeaderDict()
    for chave, valor in resposta.headers.multi_items():
        if chave.lower() not in ("content-encoding", "content-length"):
            cabecalhos.add(chave, valor)
    return HTTPResponse(
        body=io.BytesIO(resposta.content),
        headers=cabecalhos,
        status=resposta.status_code,
        reason=resposta.reason,
        preload_content=False,
    )


def _importar_curl_cffi() -> ModuleType:
    """O módulo ``curl_cffi.requests``, ou ``ImportError`` com a instrução de instalação."""
    try:
        return importlib.import_module("curl_cffi.requests")
    except ImportError as exc:
        raise ImportError(MENSAGEM_SEM_EXTRA) from exc


def tls_navegador_disponivel() -> bool:
    """Diz se o ``curl_cffi`` (extra ``juscraper[tls]``) pode ser importado."""
    try:
        _importar_curl_cffi()
    except ImportError:
        return False
    return True


def montar_tls_navegador(session: requests.Session, bases: list[str]) -> None:
    """Monta :class:`TLSNavegadorAdapter` em ``session`` para as URLs que começam com cada base."""
    adapter = TLSNavegadorAdapter()
    for base in bases:
        session.mount(base.rstrip("/") + "/", adapter)
