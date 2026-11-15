"""Adapter de TLS de navegador do TRF3 (``curl_cffi``), com um ``curl_cffi`` falso.

O ``curl_cffi`` é extra opcional e não está no ambiente do CI: os testes
injetam um módulo falso em ``sys.modules``. A fixture ``_tls_navegador_pelo_mock``
do ``tests/conftest.py`` troca ``send`` pelo do ``HTTPAdapter``; aqui o
``send`` original é restaurado quando o teste precisa dele.
"""
from __future__ import annotations

import sys
import types

import pytest
import requests

import juscraper as jus
from juscraper.courts.trf3.download import BASE_URL_1G, BASE_URL_2G
from juscraper.courts.trf3.transporte import TLSNavegadorAdapter

SEND_ORIGINAL = TLSNavegadorAdapter.__dict__["send"]
URL_BUSCA = f"{BASE_URL_2G}/v1/processos?page=0&numeroProcesso=5021122-65.2018.4.03.6100"


# Hierarquia do ``curl_cffi.requests.exceptions`` (0.17) usada pelo adapter.
class _CurlErro(OSError):
    pass


class _CurlTimeout(_CurlErro):
    pass


class _CurlConexao(_CurlErro):
    pass


class _CurlConnectTimeout(_CurlConexao, _CurlTimeout):
    pass


class _CurlProxy(_CurlErro):
    pass


class _CurlHTTPError(_CurlErro):
    """No ``curl_cffi``, erro de transporte HTTP (stream HTTP/2 reiniciado), não status."""


class _CurlChunked(_CurlErro):
    pass


class _CurlURLInvalida(_CurlErro):
    pass


class _CabecalhosCurl:
    """Os ``Headers`` do ``curl_cffi``: ``items()`` junta repetidos com vírgula, ``multi_items()`` não."""

    def __init__(self, pares: list[tuple[str, str]]) -> None:
        self.pares = pares

    def multi_items(self) -> list[tuple[str, str]]:
        return list(self.pares)


class _RespostaCurl:
    status_code = 200
    content = '{"status": "ok", "result": []}'.encode()
    reason = "OK"

    def __init__(self, url: str) -> None:
        self.url = url
        # Content-Length do corpo comprimido, menor que o corpo já descomprimido.
        self.headers = _CabecalhosCurl([
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Encoding", "gzip"),
            ("Content-Length", "7"),
            ("Set-Cookie", "bm_sz=1; Path=/"),
            ("Set-Cookie", "_abck=2; Path=/"),
        ])


class _CurlFalso:
    """O módulo ``curl_cffi.requests`` falso; guarda as sessões criadas e o erro a levantar."""

    def __init__(self) -> None:
        self.sessoes: list[_SessaoCurl] = []
        self.erro: Exception | None = None
        self.exceptions = types.SimpleNamespace(
            RequestException=_CurlErro,
            Timeout=_CurlTimeout,
            ConnectTimeout=_CurlConnectTimeout,
            ConnectionError=_CurlConexao,
            ProxyError=_CurlProxy,
            HTTPError=_CurlHTTPError,
            ChunkedEncodingError=_CurlChunked,
        )
        self.Session = self._nova_sessao

    def _nova_sessao(self, impersonate: str) -> _SessaoCurl:
        self.sessoes.append(_SessaoCurl(self, impersonate))
        return self.sessoes[-1]


class _SessaoCurl:
    def __init__(self, modulo: _CurlFalso, impersonate: str) -> None:
        self.modulo = modulo
        self.impersonate = impersonate
        self.chamadas: list[tuple[str, str, dict]] = []
        self.fechada = False

    def request(self, method: str, url: str, **kwargs):
        self.chamadas.append((method, url, kwargs))
        if self.modulo.erro is not None:
            raise self.modulo.erro
        return _RespostaCurl(url)

    def close(self) -> None:
        self.fechada = True


@pytest.fixture
def curl_falso(monkeypatch):
    """Instala um ``curl_cffi.requests`` falso e restaura o ``send`` do adapter."""
    modulo = _CurlFalso()
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", modulo)
    monkeypatch.setattr(TLSNavegadorAdapter, "send", SEND_ORIGINAL)
    return modulo


def _sessao_com_adapter() -> requests.Session:
    session = requests.Session()
    session.mount(f"{BASE_URL_2G}/", TLSNavegadorAdapter())
    session.headers.update({"Connection": "keep-alive", "Accept-Encoding": "gzip", "x-pagina-origem": "origem"})
    return session


def test_scraper_monta_adapter_so_na_consulta_processual():
    sessao = jus.scraper("trf3").session
    assert isinstance(sessao.get_adapter(f"{BASE_URL_1G}/v1/processos"), TLSNavegadorAdapter)
    assert isinstance(sessao.get_adapter(URL_BUSCA), TLSNavegadorAdapter)
    assert not isinstance(sessao.get_adapter("https://web.trf3.jus.br/jurisprudencia"), TLSNavegadorAdapter)


def test_envia_pelo_curl_com_tls_do_chrome_e_converte_resposta(curl_falso):
    resp = _sessao_com_adapter().get(URL_BUSCA, timeout=(10.0, 20.0))

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "result": []}
    assert resp.encoding == "utf-8"
    assert resp.url == URL_BUSCA
    assert "Content-Encoding" not in resp.headers
    assert "Content-Length" not in resp.headers
    [sessao] = curl_falso.sessoes
    assert sessao.impersonate == "chrome"
    [(method, url, kwargs)] = sessao.chamadas
    assert (method, url) == ("GET", URL_BUSCA)
    assert kwargs["timeout"] == (10.0, 20.0)
    assert kwargs["allow_redirects"] is False
    assert kwargs["headers"]["x-pagina-origem"] == "origem"
    assert not {"connection", "accept-encoding"} & {k.lower() for k in kwargs["headers"]}
    assert kwargs["verify"] is True


def test_set_cookie_repetido_chega_separado(curl_falso):
    resp = _sessao_com_adapter().get(URL_BUSCA)

    assert resp.raw.headers.getlist("Set-Cookie") == ["bm_sz=1; Path=/", "_abck=2; Path=/"]


def test_caminho_de_ca_segue_para_o_curl(curl_falso):
    session = _sessao_com_adapter()
    session.verify = "/caminho/ca.pem"
    session.get(URL_BUSCA)

    [sessao] = curl_falso.sessoes
    assert sessao.chamadas[0][2]["verify"] == "/caminho/ca.pem"


def test_reusa_a_sessao_curl_e_fecha_com_a_sessao_requests(curl_falso):
    session = _sessao_com_adapter()
    session.get(URL_BUSCA)
    session.get(URL_BUSCA)
    session.close()

    [sessao] = curl_falso.sessoes
    assert len(sessao.chamadas) == 2
    assert sessao.fechada


@pytest.mark.parametrize(
    ("erro", "esperada"),
    [
        (_CurlConnectTimeout("connect timed out"), requests.ConnectTimeout),
        (_CurlTimeout("operation timed out"), requests.ReadTimeout),
        (_CurlConexao("connection refused"), requests.ConnectionError),
        (_CurlProxy("proxy"), requests.ConnectionError),
        (_CurlHTTPError("HTTP/2 stream 3 reset by server"), requests.ConnectionError),
        (_CurlChunked("chunked"), requests.ConnectionError),
        (_CurlErro("código do curl sem classe própria"), requests.ConnectionError),
    ],
)
def test_erros_de_transporte_do_curl_viram_excecoes_do_requests(curl_falso, erro, esperada):
    curl_falso.erro = erro
    session = _sessao_com_adapter()

    with pytest.raises(esperada):
        session.get(URL_BUSCA)


def test_erro_de_configuracao_do_curl_sobe_como_veio(curl_falso):
    curl_falso.erro = _CurlURLInvalida("URL inválida")

    with pytest.raises(_CurlURLInvalida):
        _sessao_com_adapter().get(URL_BUSCA)


def test_sem_o_extra_cposg_levanta_import_error_com_a_instalacao(monkeypatch):
    monkeypatch.setitem(sys.modules, "curl_cffi", None)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", None)
    monkeypatch.setattr(TLSNavegadorAdapter, "send", SEND_ORIGINAL)

    with pytest.raises(ImportError, match=r"juscraper\[tls\]"):
        jus.scraper("trf3").cposg("5021122-65.2018.4.03.6100")
