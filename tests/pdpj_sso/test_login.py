"""Login gov.br com um Playwright falso (sem navegador nem rede)."""
import asyncio
import os
import signal
import subprocess
import sys
import threading
import time
import types
from contextlib import contextmanager
from typing import Any, cast

import pytest

from juscraper.aggregators._pdpj_sso import login
from juscraper.aggregators._pdpj_sso.credencial import CredencialPdpj
from juscraper.aggregators._pdpj_sso.login import PORTAL_CONSULTA, obter_credencial_govbr
from tests.pdpj_sso._jwt import token

_SSO = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth?client_id=x"
_TOKEN = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
_API = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/?numeroProcesso=1"
# O login so aceita bearer que seja JWT; os nomes ficam no claim ``sub``.
_DO_PORTAL = token(sub="do-portal")
_DE_FORA = token(sub="de-fora")
_APOS_RELOAD = token(sub="apos-reload")


def _requisicao(url, bearer):
    return "request", types.SimpleNamespace(url=url, headers={"authorization": f"Bearer {bearer}"})


def _resposta_token(dados, ok=True):
    return "response", types.SimpleNamespace(
        url=_TOKEN, ok=ok, request=types.SimpleNamespace(method="POST"), json=lambda: dados,
    )


class _ErroFalso(Exception):
    """Faz o papel de ``playwright.sync_api.Error``."""


class _TimeoutFalso(_ErroFalso):
    """Faz o papel de ``playwright.sync_api.TimeoutError``, subclasse do ``Error``.

    Nao e o ``TimeoutError`` nativo: se o codigo tolerasse o nativo no lugar do
    do Playwright, os testes de portal lento ficariam vermelhos.
    """


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
        self.goto_kwargs: list[dict] = []

    @property
    def url(self):
        return self._urls[min(self.passo, len(self._urls) - 1)]

    def is_closed(self):
        return self._fecha_no_passo is not None and self.passo >= self._fecha_no_passo

    def goto(self, url, **kwargs):
        self.gotos.append(url)
        self.goto_kwargs.append(kwargs)
        if len(self.gotos) > 1:
            self._context.disparar(self._eventos.get("goto", []))

    def wait_for_timeout(self, _ms):
        self.passo += 1
        self._context.disparar(self._eventos.get(self.passo, []))


class _Context:
    def __init__(self, urls, eventos, fecha_no_passo):
        self.handlers: dict[str, list] = {}
        self.page = _Page(self, urls, eventos, fecha_no_passo)
        self.pages = [self.page]

    def on(self, evento, handler):
        self.handlers.setdefault(evento, []).append(handler)

    def new_page(self):
        return self.page

    def disparar(self, eventos):
        for nome, objeto in eventos:
            for handler in self.handlers.get(nome, []):
                handler(objeto)


class _Browser:
    def __init__(self, context, processo):
        self.context = context
        self.contexts = [context]
        self.processo = processo


class _Processo:
    returncode = 0

    def __init__(self):
        self.encerrado = False

    def poll(self):
        return 0 if self.encerrado else None

    def terminate(self):
        self.encerrado = True

    def wait(self, timeout=None):
        return 0


def _instalar_playwright_falso(mocker, urls, eventos, fecha_no_passo=None):
    """Substitui o Playwright e a abertura do navegador.

    Devolve o mock do ``connect_over_cdp`` e o browser falso; ``browser.processo``
    e o processo falso do navegador, para conferir que ele foi encerrado.
    """
    browser = _Browser(_Context(urls, eventos, fecha_no_passo), _Processo())
    launch = mocker.Mock(return_value=browser)
    mocker.patch.object(login, "localizar_navegador", return_value="/usr/bin/google-chrome")
    mocker.patch.object(login, "abrir_navegador", return_value=(browser.processo, 9222))

    @contextmanager
    def sync_playwright():
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        yield types.SimpleNamespace(chromium=types.SimpleNamespace(connect_over_cdp=launch))

    sync_api = types.ModuleType("playwright.sync_api")
    vars(sync_api)["sync_playwright"] = sync_playwright
    vars(sync_api)["Error"] = _ErroFalso
    vars(sync_api)["TimeoutError"] = _TimeoutFalso
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

    assert obter_credencial_govbr(timeout=5) == CredencialPdpj("acesso", "renovacao")

    launch.assert_called_once_with("http://127.0.0.1:9222")
    assert browser.context.page.gotos == [PORTAL_CONSULTA]
    assert browser.processo.encerrado


def test_so_o_cabecalho_da_access_sem_refresh_e_ignora_host_de_fora(mocker):
    _, browser = _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, PORTAL_CONSULTA],
        {
            1: [_requisicao("https://www.gov.br/api", _DE_FORA)],
            2: [_requisicao(_API, _DO_PORTAL)],
        },
    )

    assert obter_credencial_govbr(timeout=5) == CredencialPdpj(_DO_PORTAL, None)
    assert browser.processo.encerrado


def test_resposta_de_token_com_erro_e_ignorada(mocker):
    _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, PORTAL_CONSULTA],
        {
            1: [_resposta_token({"access_token": "nao-deveria"}, ok=False)],
            2: [_requisicao(_API, _DO_PORTAL)],
        },
    )

    assert obter_credencial_govbr(timeout=5) == CredencialPdpj(_DO_PORTAL, None)


def test_volta_ao_portal_sem_token_recarrega_a_consulta_uma_vez(mocker):
    _, browser = _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, "https://portaldeservicos.pdpj.jus.br/home"],
        {"goto": [_requisicao(_API, _APOS_RELOAD)]},
    )

    # Prazo curto: se o reload regredir, o teste falha em segundos em vez de esperar 300 s.
    assert obter_credencial_govbr(timeout=5) == CredencialPdpj(_APOS_RELOAD, None)
    assert browser.context.page.gotos == [PORTAL_CONSULTA, PORTAL_CONSULTA]


def test_sem_token_ate_o_prazo_levanta_e_fecha_o_navegador(mocker):
    _, browser = _instalar_playwright_falso(mocker, [PORTAL_CONSULTA], {})
    mocker.patch("juscraper.aggregators._pdpj_sso.login.time.monotonic", side_effect=[0.0, 0.0, 0.0, 0.0, 500.0])

    with pytest.raises(RuntimeError, match="auth\\(token\\)"):
        obter_credencial_govbr(timeout=300)

    assert browser.processo.encerrado


def test_janela_fechada_levanta(mocker):
    _, browser = _instalar_playwright_falso(mocker, [PORTAL_CONSULTA, _SSO], {}, fecha_no_passo=2)

    with pytest.raises(RuntimeError, match="fechada"):
        obter_credencial_govbr(timeout=5)

    assert browser.processo.encerrado


def test_sem_playwright_orienta_a_instalar_o_extra(mocker):
    mocker.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None})

    with pytest.raises(ImportError, match=r"juscraper\[govbr\]"):
        obter_credencial_govbr()


def test_localizar_navegador_usa_o_primeiro_instalado(mocker):
    mocker.patch.object(login.shutil, "which", side_effect=lambda nome: "/opt/chromium" if nome == "chromium" else None)
    assert login.localizar_navegador() == "/opt/chromium"


def test_localizar_navegador_sem_nenhum_instalado_levanta(mocker):
    mocker.patch.object(login.shutil, "which", return_value=None)
    mocker.patch.object(login, "_CAMINHOS_NAVEGADOR", ())
    with pytest.raises(RuntimeError, match="navegador="):
        login.localizar_navegador()


def test_localizar_navegador_informado_inexistente_levanta(mocker):
    mocker.patch.object(login.shutil, "which", return_value=None)
    with pytest.raises(RuntimeError, match="nao encontrado"):
        login.localizar_navegador("/nao/existe/chrome")


def test_abrir_navegador_le_a_porta_e_nao_liga_automacao(mocker, tmp_path):
    processo = _Processo()
    argumentos_recebidos = []

    def popen(argumentos, **_kwargs):
        (tmp_path / "DevToolsActivePort").write_text("41234\n/devtools/browser/x\n", encoding="utf-8")
        argumentos_recebidos.extend(argumentos)
        return processo

    mocker.patch.object(login.subprocess, "Popen", side_effect=popen)

    aberto, porta = login.abrir_navegador("/usr/bin/google-chrome", tmp_path)
    assert aberto is cast(Any, processo)
    assert porta == 41234
    assert f"--user-data-dir={tmp_path}" in argumentos_recebidos
    assert "--disable-blink-features=AutomationControlled" in argumentos_recebidos
    assert "--enable-automation" not in argumentos_recebidos


def test_abrir_navegador_que_fecha_ao_abrir_levanta(mocker, tmp_path):
    processo = _Processo()
    processo.encerrado = True
    mocker.patch.object(login.subprocess, "Popen", return_value=processo)

    with pytest.raises(RuntimeError, match="fechou logo ao abrir"):
        login.abrir_navegador("/usr/bin/google-chrome", tmp_path)


def test_bearer_que_nao_e_jwt_e_ignorado(mocker):
    _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, PORTAL_CONSULTA],
        {1: [_requisicao(_API, "undefined")], 2: [_requisicao(_API, _DO_PORTAL)]},
    )

    assert obter_credencial_govbr(timeout=5) == CredencialPdpj(_DO_PORTAL, None)


def test_com_bearer_espera_a_resposta_de_token_para_ter_o_refresh(mocker, monkeypatch):
    # Espera real maior que os passos do falso: a resposta de token chega dois
    # passos depois do cabecalho e ainda dentro da janela de espera.
    monkeypatch.setattr(login, "ESPERA_PELO_REFRESH", 30.0)
    _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, PORTAL_CONSULTA],
        {
            2: [_requisicao(_API, _DO_PORTAL)],
            4: [_resposta_token({"access_token": _DO_PORTAL, "refresh_token": "renovacao"})],
        },
    )

    assert obter_credencial_govbr(timeout=5) == CredencialPdpj(_DO_PORTAL, "renovacao")


def test_reload_lento_nao_interrompe_a_espera(mocker):
    _, browser = _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, "https://portaldeservicos.pdpj.jus.br/home"],
        {6: [_requisicao(_API, _APOS_RELOAD)]},
    )
    goto_original = _Page.goto

    def goto(self, url, **kwargs):
        goto_original(self, url, **kwargs)
        if len(self.gotos) > 1:
            raise _TimeoutFalso("Timeout 30000ms exceeded")

    mocker.patch.object(_Page, "goto", goto)

    assert obter_credencial_govbr(timeout=5) == CredencialPdpj(_APOS_RELOAD, None)
    assert browser.processo.encerrado


def test_cancelamento_encerra_a_espera(mocker):
    _instalar_playwright_falso(mocker, [PORTAL_CONSULTA], {})
    cancelar = threading.Event()
    cancelar.set()
    page = types.SimpleNamespace(is_closed=lambda: False)

    with pytest.raises(RuntimeError, match="cancelado"):
        login._esperar_credencial(page, login._Captura(), 5, cancelar, _ErroFalso)


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT enviado ao proprio processo")
def test_ctrl_c_chega_ao_chamador_sem_esperar_o_worker(mocker):
    cancelado = threading.Event()

    def worker(_timeout, _navegador, sessao):
        sessao.cancelar.wait(10)
        cancelado.set()
        raise RuntimeError("Login no gov.br cancelado.")

    mocker.patch.object(login, "_obter_credencial", side_effect=worker)
    # SIGINT real, como o do Ctrl-C: ``interrupt_main`` nao acorda o ``result()`` bloqueado.
    threading.Timer(0.2, os.kill, args=(os.getpid(), signal.SIGINT)).start()
    inicio = time.monotonic()

    with pytest.raises(KeyboardInterrupt):
        obter_credencial_govbr(timeout=5)

    assert time.monotonic() - inicio < 5
    assert cancelado.wait(5)


def test_abrir_navegador_sem_porta_no_prazo_encerra_o_processo(mocker, tmp_path):
    processo = _Processo()
    mocker.patch.object(login.subprocess, "Popen", return_value=processo)
    mocker.patch.object(login, "ESPERA_PELA_PORTA", 0.3)

    with pytest.raises(RuntimeError, match="porta de depuracao"):
        login.abrir_navegador("/usr/bin/google-chrome", tmp_path)

    assert processo.encerrado


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT enviado ao proprio processo")
def test_ctrl_c_nao_espera_worker_preso(mocker):
    """Worker preso num passo que nao confere o cancelamento (``goto`` longo, por exemplo)."""
    mocker.patch.object(login, "_obter_credencial", side_effect=lambda *_a: time.sleep(3))
    threading.Timer(0.2, os.kill, args=(os.getpid(), signal.SIGINT)).start()
    inicio = time.monotonic()

    with pytest.raises(KeyboardInterrupt):
        obter_credencial_govbr(timeout=5)

    assert time.monotonic() - inicio < 2


def test_timeout_de_navegacao_tem_teto_e_respeita_o_prazo():
    assert login._timeout_de_navegacao(prazo=1000.0, agora=0.0) == login.TIMEOUT_NAVEGACAO * 1000
    assert login._timeout_de_navegacao(prazo=10.0, agora=5.0) == 5000
    assert login._timeout_de_navegacao(prazo=10.0, agora=9.9) == 1000


def test_toda_navegacao_do_portal_respeita_o_teto(mocker):
    """Abertura e reload: nenhum ``goto`` espera o prazo inteiro do login."""
    _, browser = _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, "https://portaldeservicos.pdpj.jus.br/home"],
        {"goto": [_requisicao(_API, _APOS_RELOAD)]},
    )

    obter_credencial_govbr(timeout=300)

    timeouts = [kwargs["timeout"] for kwargs in browser.context.page.goto_kwargs]
    assert len(timeouts) == 2
    assert all(t <= login.TIMEOUT_NAVEGACAO * 1000 for t in timeouts)


def test_abertura_lenta_do_portal_nao_interrompe_a_espera(mocker):
    _instalar_playwright_falso(mocker, [PORTAL_CONSULTA, _SSO, PORTAL_CONSULTA], {2: [_requisicao(_API, _DO_PORTAL)]})
    goto_original = _Page.goto

    def goto(self, url, **kwargs):
        goto_original(self, url, **kwargs)
        raise _TimeoutFalso("Timeout 30000ms exceeded")

    mocker.patch.object(_Page, "goto", goto)

    assert obter_credencial_govbr(timeout=5) == CredencialPdpj(_DO_PORTAL, None)


def test_cancelar_fecha_o_navegador_registrado():
    processo = _Processo()
    sessao = login._SessaoLogin()
    sessao.processo = cast(Any, processo)

    sessao.cancelar_e_fechar()

    assert sessao.cancelar.is_set()
    assert processo.encerrado


def test_abrir_navegador_cancelado_encerra_o_processo(mocker, tmp_path):
    processo = _Processo()
    mocker.patch.object(login.subprocess, "Popen", return_value=processo)
    sessao = login._SessaoLogin()
    sessao.cancelar.set()

    with pytest.raises(RuntimeError, match="cancelado"):
        login.abrir_navegador("/usr/bin/google-chrome", tmp_path, sessao)

    assert sessao.processo is cast(Any, processo)
    assert processo.encerrado


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT enviado ao proprio processo")
def test_ctrl_c_com_worker_preso_nao_segura_a_saida_do_interpretador():
    """O worker e daemon: o processo sai logo depois do Ctrl-C, sem esperar o ``goto`` preso."""
    codigo = (
        "import os, signal, threading, time\n"
        "from juscraper.aggregators._pdpj_sso import login\n"
        "login._obter_credencial = lambda *_a: time.sleep(20)\n"
        "threading.Timer(0.3, os.kill, args=(os.getpid(), signal.SIGINT)).start()\n"
        "login.obter_credencial_govbr(timeout=5)\n"
    )
    inicio = time.monotonic()
    completado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)

    assert "KeyboardInterrupt" in completado.stderr
    assert time.monotonic() - inicio < 10


def test_erro_de_rede_na_abertura_sobe_na_hora(mocker):
    _instalar_playwright_falso(mocker, ["chrome-error://chromewebdata/"], {})
    erro_de_rede = _ErroFalso("net::ERR_NAME_NOT_RESOLVED at https://portaldeservicos")
    mocker.patch.object(_Page, "goto", side_effect=erro_de_rede)
    inicio = time.monotonic()

    with pytest.raises(_ErroFalso, match="ERR_NAME_NOT_RESOLVED"):
        obter_credencial_govbr(timeout=5)

    assert time.monotonic() - inicio < 2


def test_janela_fechada_durante_a_navegacao_diz_que_fechou(mocker):
    _instalar_playwright_falso(mocker, [PORTAL_CONSULTA], {}, fecha_no_passo=0)
    mocker.patch.object(_Page, "goto", side_effect=_ErroFalso("Target page, context or browser has been closed"))

    with pytest.raises(RuntimeError, match="fechada"):
        obter_credencial_govbr(timeout=5)


def test_reload_interrompido_por_outra_navegacao_nao_derruba_o_login(mocker):
    """Um clique do usuario antes do commit aborta o reload; o token chega pela navegacao dele."""
    _, browser = _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, "https://portaldeservicos.pdpj.jus.br/home"],
        {6: [_requisicao(_API, _APOS_RELOAD)]},
    )
    goto_original = _Page.goto

    def goto(self, url, **kwargs):
        goto_original(self, url, **kwargs)
        if len(self.gotos) > 1:
            raise _ErroFalso(f'Navigation to "{url}" is interrupted by another navigation')

    mocker.patch.object(_Page, "goto", goto)

    assert obter_credencial_govbr(timeout=5) == CredencialPdpj(_APOS_RELOAD, None)
    assert browser.processo.encerrado


def test_erro_fora_do_playwright_no_reload_sobe(mocker):
    """Bug no codigo nao e navegacao interrompida: so o ``Error`` do Playwright e tolerado no reload."""
    _instalar_playwright_falso(
        mocker,
        [PORTAL_CONSULTA, _SSO, "https://portaldeservicos.pdpj.jus.br/home"],
        {6: [_requisicao(_API, _APOS_RELOAD)]},
    )
    goto_original = _Page.goto

    def goto(self, url, **kwargs):
        goto_original(self, url, **kwargs)
        if len(self.gotos) > 1:
            raise AttributeError("bug no reload")

    mocker.patch.object(_Page, "goto", goto)

    with pytest.raises(AttributeError, match="bug no reload"):
        obter_credencial_govbr(timeout=5)
