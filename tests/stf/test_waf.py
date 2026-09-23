"""Obtencao do cookie aws-waf-token com um Playwright falso (sem navegador nem rede)."""
import asyncio
import sys
import types
from contextlib import contextmanager

import pytest
import responses

import juscraper as jus
from juscraper.courts.stf._waf import PAGINA_BUSCA, USER_AGENT, WAF_COOKIE, obter_waf_token
from juscraper.courts.stf.download import BASE_URL
from tests._helpers import load_sample


class _Page:
    def __init__(self, context):
        self._context = context
        self.gotos: list[tuple[str, dict]] = []

    def goto(self, url, **kwargs):
        self.gotos.append((url, kwargs))

    def wait_for_timeout(self, _ms):
        self._context.esperas += 1


class _Context:
    def __init__(self, cookies_por_espera):
        self._cookies_por_espera = cookies_por_espera
        self.esperas = 0
        self.page = None

    def new_page(self):
        self.page = _Page(self)
        return self.page

    def cookies(self):
        return self._cookies_por_espera[min(self.esperas, len(self._cookies_por_espera) - 1)]


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


def _instalar_playwright_falso(mocker, cookies_por_espera):
    context = _Context(cookies_por_espera)
    browser = _Browser(context)
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


def test_devolve_o_cookie_quando_o_desafio_termina(mocker):
    sem_cookie = [{"name": "AWSALB", "value": "x"}]
    com_cookie = [*sem_cookie, {"name": WAF_COOKIE, "value": "token-resolvido"}]
    launch, browser = _instalar_playwright_falso(mocker, [sem_cookie, sem_cookie, com_cookie])

    assert obter_waf_token() == "token-resolvido"

    launch.assert_called_once_with(headless=True, channel="chromium")
    assert browser.context_kwargs == {"user_agent": USER_AGENT, "locale": "pt-BR"}
    assert browser.context.page.gotos[0][0] == PAGINA_BUSCA
    assert browser.context.esperas == 2
    assert browser.fechado


def test_sem_cookie_ate_o_prazo_levanta_e_fecha_o_navegador(mocker):
    _, browser = _instalar_playwright_falso(mocker, [[]])
    mocker.patch("juscraper.courts.stf._waf.time.monotonic", side_effect=[0.0, 0.0, 100.0])

    with pytest.raises(RuntimeError, match=WAF_COOKIE):
        obter_waf_token(timeout=60)

    assert browser.fechado


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_token", [None, "token-expirado"])
async def test_acquisition_and_renewal_with_running_loop(mocker, existing_token):
    _, browser = _instalar_playwright_falso(mocker, [[{"name": WAF_COOKIE, "value": "token-novo"}]])
    stf = jus.scraper("stf", waf_token=existing_token)
    loop = asyncio.get_running_loop()
    with responses.RequestsMock() as mocked:
        if existing_token is not None:
            mocked.add(responses.POST, BASE_URL, status=202, headers={"x-amzn-waf-action": "challenge"})
        mocked.add(
            responses.POST, BASE_URL,
            body=load_sample("stf", "listar_decisoes/no_results.json"), content_type="application/json",
        )
        df = stf.contar_decisoes("juscraper_probe_zero_hits_xyzqwe")
        assert mocked.calls[-1].request.headers["Cookie"] == "aws-waf-token=token-novo"
        assert len(mocked.calls) == (2 if existing_token else 1)
    assert df.iloc[0]["n"] == 0
    assert asyncio.get_running_loop() is loop
    assert browser.fechado


@pytest.mark.parametrize("operation", ["new_context", "goto"])
def test_browser_error_closes_browser_and_propagates(mocker, operation):
    _, browser = _instalar_playwright_falso(mocker, [[]])
    error = RuntimeError("Falha do navegador")
    target = browser if operation == "new_context" else _Page
    mocker.patch.object(target, operation, side_effect=error)

    with pytest.raises(RuntimeError, match="Falha do navegador") as caught:
        obter_waf_token()

    assert caught.value is error
    assert browser.fechado
