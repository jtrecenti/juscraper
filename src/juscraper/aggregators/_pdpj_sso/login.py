"""Login no gov.br no Chrome da maquina, para capturar o token do PDPJ.

O login do SSO do PJe passa pelo gov.br, que pede captcha e segundo fator,
entao a pessoa faz o login na janela e o codigo so observa o trafego. Duas
escutas capturam o token: a resposta do endpoint de token do SSO, que traz
access e refresh token, e, como reserva, o cabecalho ``Authorization`` das
chamadas do portal a ``*.pdpj.jus.br``, que traz so o access token.

O navegador nao e lancado pelo Playwright. O ``launch()`` dele liga
``--enable-automation`` e deixa ``navigator.webdriver`` verdadeiro, e o
captcha do gov.br recusa a resposta de um navegador marcado como automatizado
mesmo quando ela esta certa. Por isso o Chrome (ou Chromium, ou Edge)
instalado abre como processo comum, com perfil temporario e porta de
depuracao, e o Playwright so se conecta por CDP para escutar a rede.
"""
from __future__ import annotations

import logging
import shutil
import subprocess  # nosec B404
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jwt

from .credencial import CredencialPdpj, ler_exp

logger = logging.getLogger(__name__)

PORTAL_CONSULTA = "https://portaldeservicos.pdpj.jus.br/consulta"
_HOST_PORTAL = "portaldeservicos.pdpj.jus.br"
_SUFIXO_PDPJ = ".pdpj.jus.br"
_CAMINHO_TOKEN = "/protocol/openid-connect/token"  # nosec B105
# Depois de voltar ao portal, a pagina ainda troca o ``code`` pelo token; o
# reload antes disso interromperia a troca.
ESPERA_ANTES_DO_RELOAD = 3.0
# Com o access token em maos, quanto esperar pela resposta do endpoint de
# token, que traz tambem o refresh.
ESPERA_PELO_REFRESH = 5.0
# Prazo para o navegador recem-aberto publicar a porta de depuracao.
ESPERA_PELA_PORTA = 30.0

_NOMES_NAVEGADOR = (
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "microsoft-edge-stable", "chrome", "msedge",
)
_CAMINHOS_NAVEGADOR = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def obter_credencial_govbr(timeout: float = 300.0, navegador: str | None = None) -> CredencialPdpj:
    """Abre o portal de servicos do PDPJ, espera o login e devolve a credencial.

    Args:
        timeout (float): Segundos para a pessoa concluir o login. Default ``300``.
        navegador (str | None): Executavel do Chrome, Chromium ou Edge. ``None``
            procura um instalado. Default ``None``.

    Returns:
        CredencialPdpj: Access token e, quando o SSO o entrega ao navegador,
        refresh token.

    Raises:
        ImportError: Quando o Playwright nao esta instalado (extra ``juscraper[govbr]``).
        RuntimeError: Quando nao ha navegador, a janela e fechada ou o prazo
            acaba sem token.
    """
    # O Playwright sincrono exige uma thread sem o loop ativo do Jupyter. Sem
    # ``with``: a saida do ``with`` esperaria o worker, e o Ctrl-C so chegaria
    # quando a janela fechasse. O evento avisa o worker para fechar o navegador.
    cancelar = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1)
    futuro = executor.submit(_obter_credencial, timeout, navegador, cancelar)
    concluiu = False
    try:
        credencial = futuro.result()
        concluiu = True
        return credencial
    finally:
        if not concluiu:
            cancelar.set()
        executor.shutdown(wait=False)


def localizar_navegador(navegador: str | None = None) -> str:
    """Devolve o executavel do navegador: o informado ou o primeiro instalado.

    Raises:
        RuntimeError: Quando nenhum Chrome, Chromium ou Edge e encontrado.
    """
    if navegador is not None:
        encontrado = shutil.which(navegador) or (navegador if Path(navegador).is_file() else None)
        if encontrado is None:
            raise RuntimeError(f"Navegador nao encontrado: {navegador}")
        return encontrado
    for nome in _NOMES_NAVEGADOR:
        encontrado = shutil.which(nome)
        if encontrado is not None:
            return encontrado
    for caminho in _CAMINHOS_NAVEGADOR:
        if Path(caminho).is_file():
            return caminho
    raise RuntimeError(
        "O login pelo gov.br precisa do Google Chrome, Chromium ou Microsoft Edge instalado. "
        "Instale um deles ou informe o executavel em auth_govbr(navegador=...)."
    )


def abrir_navegador(executavel: str, perfil: Path) -> tuple[subprocess.Popen[bytes], int]:
    """Abre o navegador como processo comum e devolve o processo e a porta CDP.

    ``--remote-debugging-port=0`` deixa o navegador escolher uma porta livre e
    grava-la em ``DevToolsActivePort``, no diretorio do perfil. O perfil
    temporario e obrigatorio: o Chrome recusa a porta de depuracao no perfil
    padrao da pessoa, e o login nao deve se misturar com ele.

    Raises:
        RuntimeError: Quando o navegador fecha ou nao publica a porta no prazo.
    """
    # Sem ``with``: o processo sobrevive a esta funcao e e encerrado por ``_encerrar``.
    processo = subprocess.Popen(  # nosec B603  # pylint: disable=consider-using-with
        [
            executavel,
            f"--user-data-dir={perfil}",
            "--remote-debugging-port=0",
            "--no-first-run",
            "--no-default-browser-check",
            "--lang=pt-BR",
            # Com a porta de depuracao aberta, o Chrome liga ``navigator.webdriver``;
            # sem esta flag o captcha do gov.br recusa a resposta da pessoa.
            "--disable-blink-features=AutomationControlled",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    arquivo_porta = perfil / "DevToolsActivePort"
    prazo = time.monotonic() + ESPERA_PELA_PORTA
    while time.monotonic() < prazo:
        if processo.poll() is not None:
            raise RuntimeError(f"O navegador {executavel} fechou logo ao abrir (codigo {processo.returncode}).")
        linhas = arquivo_porta.read_text(encoding="utf-8").split() if arquivo_porta.exists() else []
        if linhas and linhas[0].isdigit():
            return processo, int(linhas[0])
        time.sleep(0.2)
    _encerrar(processo)
    raise RuntimeError(f"O navegador {executavel} nao abriu a porta de depuracao em {ESPERA_PELA_PORTA:.0f}s.")


def _encerrar(processo: subprocess.Popen[bytes]) -> None:
    if processo.poll() is not None:
        return
    processo.terminate()
    try:
        processo.wait(timeout=10)
    except subprocess.TimeoutExpired:
        processo.kill()
        processo.wait()


def _obter_credencial(timeout: float, navegador: str | None, cancelar: threading.Event) -> CredencialPdpj:
    try:
        from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "O login pelo gov.br precisa do Playwright. Instale com "
            "`pip install 'juscraper[govbr]'`, ou passe um token ja obtido em "
            "`auth(token)` ou na variavel PDPJ_JWT."
        ) from exc

    executavel = localizar_navegador(navegador)
    # ``ignore_cleanup_errors``: no Windows, processos filhos do navegador podem
    # segurar arquivos do perfil por um instante, e o erro da limpeza trocaria a
    # credencial ja obtida por uma excecao.
    with tempfile.TemporaryDirectory(prefix="juscraper-govbr-", ignore_cleanup_errors=True) as diretorio:
        processo, porta = abrir_navegador(executavel, Path(diretorio))
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
                context = browser.contexts[0]
                captura = _Captura()
                context.on("request", captura.ao_requisitar)
                context.on("response", captura.ao_responder)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(PORTAL_CONSULTA, wait_until="domcontentloaded", timeout=timeout * 1000)
                return _esperar_credencial(page, captura, timeout, cancelar)
        finally:
            _encerrar(processo)


class _Captura:
    """Guarda o que as escutas do navegador veem.

    Os handlers so enfileiram: ler o corpo de uma resposta dentro do handler
    bloquearia o despacho de eventos do Playwright sincrono. O corpo e lido em
    :meth:`processar`, chamado pelo laco de espera.
    """

    def __init__(self) -> None:
        self.bearer: str | None = None
        self.credencial: CredencialPdpj | None = None
        self._respostas_token: list[Any] = []

    def ao_requisitar(self, request: Any) -> None:
        if self.bearer is not None:
            return
        host = urlparse(request.url).hostname or ""
        if not host.endswith(_SUFIXO_PDPJ):
            return
        valor = request.headers.get("authorization", "")
        if not valor.lower().startswith("bearer "):
            return
        candidato = valor[7:].strip()
        # O front pode mandar ``Bearer undefined`` antes do login; so JWT conta.
        try:
            ler_exp(candidato)
        except jwt.InvalidTokenError:
            return
        self.bearer = candidato

    def ao_responder(self, response: Any) -> None:
        if urlparse(response.url).path.endswith(_CAMINHO_TOKEN) and response.request.method == "POST":
            self._respostas_token.append(response)

    def processar(self) -> None:
        while self._respostas_token:
            dados = _corpo_json(self._respostas_token.pop(0))
            access = dados.get("access_token")
            if isinstance(access, str) and access:
                self.credencial = CredencialPdpj(access, dados.get("refresh_token") or None)

    def resultado(self) -> CredencialPdpj | None:
        if self.credencial is not None:
            return self.credencial
        return CredencialPdpj(self.bearer) if self.bearer is not None else None


def _corpo_json(response: Any) -> dict[str, Any]:
    """Corpo JSON de uma resposta bem-sucedida; qualquer outra coisa vira ``{}``."""
    if not response.ok:
        return {}
    try:
        dados = response.json()
    except Exception:  # pylint: disable=broad-except  # corpo indisponivel ou nao JSON
        return {}
    return dados if isinstance(dados, dict) else {}


def _esperar_credencial(
    page: Any,
    captura: _Captura,
    timeout: float,
    cancelar: threading.Event | None = None,
) -> CredencialPdpj:
    prazo = time.monotonic() + timeout
    saiu_do_portal = False
    voltou_em: float | None = None
    recarregou = False
    token_desde: float | None = None
    while time.monotonic() < prazo:
        if cancelar is not None and cancelar.is_set():
            raise RuntimeError("Login no gov.br cancelado.")
        if page.is_closed():
            raise RuntimeError("A janela do navegador foi fechada antes de o login terminar.")
        captura.processar()
        agora = time.monotonic()
        if captura.credencial is not None and captura.credencial.refresh_token is not None:
            return captura.credencial
        resultado = captura.resultado()
        if resultado is not None:
            token_desde = token_desde if token_desde is not None else agora
            if agora - token_desde >= ESPERA_PELO_REFRESH:
                return resultado
        elif urlparse(page.url).hostname != _HOST_PORTAL:
            saiu_do_portal = True
        elif saiu_do_portal and not recarregou:
            # De volta ao portal depois do login e sem token visto: o reload na
            # /consulta dispara as chamadas autenticadas que expoem o token.
            voltou_em = voltou_em if voltou_em is not None else agora
            if agora - voltou_em >= ESPERA_ANTES_DO_RELOAD:
                recarregou = True
                try:
                    page.goto(PORTAL_CONSULTA, wait_until="domcontentloaded", timeout=max(prazo - agora, 1.0) * 1000)
                except Exception:  # pylint: disable=broad-except
                    # Portal lento no reload nao e erro: o laco segue esperando o
                    # token ate o prazo, e janela fechada e tratada no topo do laco.
                    logger.debug("Reload da consulta nao terminou; seguindo a espera.")
        try:
            page.wait_for_timeout(500)
        except Exception as exc:  # pylint: disable=broad-except
            if page.is_closed():
                raise RuntimeError("A janela do navegador foi fechada antes de o login terminar.") from exc
            raise
    raise RuntimeError(
        f"O login no gov.br nao terminou em {timeout:.0f}s ou o portal nao expos o token. "
        "Tente de novo com um timeout maior, ou copie o token do devtools e use auth(token)."
    )
