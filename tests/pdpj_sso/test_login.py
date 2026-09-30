"""Login gov.br com um Playwright falso (sem navegador nem rede)."""
import asyncio
import sys
import types
from contextlib import contextmanager

import pytest

from juscraper.aggregators._pdpj_sso import login
from juscraper.aggregators._pdpj_sso.credencial import CredencialPdpj
from juscraper.aggregators._pdpj_sso.login import PORTAL_CONSULTA, obter_credencial_govbr

_SSO = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth?client_id=x"
_TOKEN = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
_API = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/?numeroProcesso=1"


def _requisicao(url, bearer):
    return "request", types.SimpleNamespace(url=url, headers={"authorization": f"Bearer {bearer}"})


def _resposta_token(dados, ok=True):
    return "response", types.SimpleNamespace(
        url=_TOKEN, ok=ok, request=types.SimpleNamespace(method="POST"), json=lambda: dados,
    )


class _Page:
    """Pagina cujo estado avanca um passo a cada ``wait_for_timeout``.

    ``urls[i]`` e a URL no passo ``i`` (a ultima se repete); ``eventos[i]`` sao
    disparados nas escutas do contexto ao entrar no passo ``i``, e
    ``eventos["goto"]`` quando o codigo recarrega a pagina.
    """

    def __init__(self, context, urls, eventos, fecha_no_passo):
        self._context = context
        self._urls = urls
        self._eventos = eventos
        self._fecha_no_passo = fecha_no_passo
        self.passo = 0
        self.gotos: list[str] = []

    @property
    def url(self):
        return self._urls[min(self.passo, len(self._urls) - 1)]

    def is_closed(self):
        return self._fecha_no_passo is not None and self.passo >= self._fecha_no_passo

    def goto(self, url, **_kwargs):
        self.gotos.append(url)
        if len(self.gotos) > 1:
            self._context.disparar(self._eventos.get("goto", []))

    def wait_for_timeout(self, _ms):
        self.passo += 1
        self._context.disparar(self._eventos.get(self.passo, []))


class _Context:
    def __init__(self, urls, eventos, fecha_no_passo):
        self.handlers: dict[str, list] = {}
        self.page = _Page(self, urls, eventos, fecha_no_passo)

    def on(self, evento, handler):
        self.handlers.setdefault(evento, []).append(handler)

    def new_page(self):
        return self.page

    def disparar(self, eventos):
        for nome, objeto in eventos:
            for handler in self.handlers.get(nome, []):
                handler(objeto)


class _Browser:
    def __init__(self, context):
        self.context = context
        self.context_kwargs = None
        self.fechado = False

    def new_context(self, **kwargs):
        self.context_kwargs = kwargs
        return self.context

    def close(self):
        self.fechado = True


def _instalar_playwright_falso(mocker, urls, eventos, fecha_no_passo=None):
    browser = _Browser(_Context(urls, eventos, fecha_no_passo))
    launch = mocker.Mock(return_value=browser)

    @contextmanager
    def sync_playwright():
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        yield types.SimpleNamespace(chromium=types.SimpleNamespace(launch=launch))

    sync_api = types.ModuleType("playwright.sync_api")
    vars(sync_api)["sync_playwright"] = sync_playwright
    mocker.patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.sync_api": sync_api})
    return launch, browser


@pytest.fixture(autouse=True)
def _sem_esperas(monkeypatch):
    monkeypatch.setattr(login, "ESPERA_ANTES_DO_RELOAD", 0.0)
    monkeypatch.setattr(login, "ESPERA_PELO_REFRESH", 0.0)


def test_resposta_do_endpoint_de_token_da_access_e_refresh(mocker):
    launch, browser = _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, PORTAL_CONSULTA],
        {2: [_resposta_token({"access_token": "acesso", "refresh_token": "renovacao"})]},
    )

    assert obter_credencial_govbr() == CredencialPdpj("acesso", "renovacao")

    launch.assert_called_once_with(headless=False)
    assert browser.context_kwargs == {"locale": "pt-BR"}
    assert browser.context.page.gotos == [PORTAL_CONSULTA]
    assert browser.fechado


def test_so_o_cabecalho_da_access_sem_refresh_e_ignora_host_de_fora(mocker):
    _, browser = _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, PORTAL_CONSULTA],
        {
            1: [_requisicao("https://www.gov.br/api", "de-fora")],
            2: [_requisicao(_API, "do-portal")],
        },
    )

    assert obter_credencial_govbr() == CredencialPdpj("do-portal", None)
    assert browser.fechado


def test_resposta_de_token_com_erro_e_ignorada(mocker):
    _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, PORTAL_CONSULTA],
        {
            1: [_resposta_token({"access_token": "nao-deveria"}, ok=False)],
            2: [_requisicao(_API, "do-portal")],
        },
    )

    assert obter_credencial_govbr() == CredencialPdpj("do-portal", None)


def test_volta_ao_portal_sem_token_recarrega_a_consulta_uma_vez(mocker):
    _, browser = _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, "https://portaldeservicos.pdpj.jus.br/home"],
        {"goto": [_requisicao(_API, "apos-reload")]},
    )

    # Prazo curto: se o reload regredir, o teste falha em segundos em vez de esperar 300 s.
    assert obter_credencial_govbr(timeout=5) == CredencialPdpj("apos-reload", None)
    assert browser.context.page.gotos == [PORTAL_CONSULTA, PORTAL_CONSULTA]


def test_sem_token_ate_o_prazo_levanta_e_fecha_o_navegador(mocker):
    _, browser = _instalar_playwright_falso(mocker, [PORTAL_CONSULTA], {})
    mocker.patch("juscraper.aggregators._pdpj_sso.login.time.monotonic", side_effect=[0.0, 0.0, 0.0, 500.0])

    with pytest.raises(RuntimeError, match="auth\\(token\\)"):
        obter_credencial_govbr(timeout=300)

    assert browser.fechado


def test_janela_fechada_levanta(mocker):
    _, browser = _instalar_playwright_falso(mocker, [PORTAL_CONSULTA, _SSO], {}, fecha_no_passo=2)

    with pytest.raises(RuntimeError, match="fechada"):
        obter_credencial_govbr()

    assert browser.fechado


def test_sem_playwright_orienta_a_instalar_o_extra(mocker):
    mocker.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None})

    with pytest.raises(ImportError, match=r"juscraper\[govbr\]"):
        obter_credencial_govbr()
