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
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import jwt

from .credencial import CredencialPdpj, ler_exp

if TYPE_CHECKING:  # pragma: no cover - so o verificador de tipos le este bloco
    # So para anotar: o Playwright e dependencia opcional, importada em ``_obter_credencial``.
    from playwright.sync_api import Page, Request, Response

logger = logging.getLogger(__name__)

PORTAL_CONSULTA = "https://portaldeservicos.pdpj.jus.br/consulta"
_HOST_PORTAL = "portaldeservicos.pdpj.jus.br"
_SUFIXO_PDPJ = ".pdpj.jus.br"
# Caminho do endpoint de token do SSO, nao uma senha.
_CAMINHO_TOKEN = "/protocol/openid-connect/token"  # nosec B105  # noqa: S105
# Depois de voltar ao portal, a pagina ainda troca o ``code`` pelo token; o
# reload antes disso interromperia a troca.
ESPERA_ANTES_DO_RELOAD = 3.0
# Com o access token em maos, quanto esperar pela resposta do endpoint de
# token, que traz tambem o refresh.
ESPERA_PELO_REFRESH = 5.0
# Teto de cada navegacao do portal, em segundos (o default do Playwright).
TIMEOUT_NAVEGACAO = 30.0
_JANELA_FECHADA = "A janela do navegador foi fechada antes de o login terminar."
# Prazo para o navegador recem-aberto publicar a porta de depuracao.
ESPERA_PELA_PORTA = 30.0

_NOMES_NAVEGADOR = (
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "microsoft-edge-stable", "chrome", "msedge",
)
# No macOS e no Windows o executavel costuma ficar fora do PATH. Cada sufixo
# e procurado abaixo de cada raiz de instalacao, na ordem de preferencia dos
# navegadores (Chrome antes do Edge em qualquer raiz).
_SUFIXOS_MACOS = (
    "Google Chrome.app/Contents/MacOS/Google Chrome",
    "Chromium.app/Contents/MacOS/Chromium",
    "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
_SUFIXOS_WINDOWS = (
    r"Google\Chrome\Application\chrome.exe",
    r"Microsoft\Edge\Application\msedge.exe",
)


def caminhos_navegador(sistema: str = sys.platform, ambiente: Mapping[str, str] | None = None,
                       casa: str | None = None) -> list[str]:
    """Lista os caminhos de instalacao do Chrome, Chromium e Edge fora do PATH.

    No Windows, as raizes sao as mesmas que o Playwright usa para achar o
    Chrome: ``LOCALAPPDATA`` vem primeiro, porque o Chrome se instala ali
    quando o usuario nao e administrador; as variaveis de ``Program Files``
    no lugar de ``C:`` fixo cobrem o sistema instalado em outra unidade; e
    as de ``HOMEDRIVE`` vem depois delas, para quando nao estao definidas.
    Variavel vazia e ignorada, porque viraria caminho relativo ao diretorio
    corrente. No macOS, o app pode estar tambem em ``~/Applications``.
    """
    if sistema == "darwin":
        pastas = [PurePosixPath("/Applications"), PurePosixPath(casa or Path.home()) / "Applications"]
        return [str(pasta / sufixo) for sufixo in _SUFIXOS_MACOS for pasta in pastas]
    if sistema == "win32":
        raizes = _raizes_windows(os.environ if ambiente is None else ambiente)
        return [str(PureWindowsPath(raiz, sufixo)) for sufixo in _SUFIXOS_WINDOWS for raiz in raizes]
    return []


def _raizes_windows(ambiente: Mapping[str, str]) -> list[str]:
    """Raizes de instalacao do Windows, na ordem descrita em :func:`caminhos_navegador`."""
    variaveis = ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
    raizes = [ambiente[nome] for nome in variaveis if ambiente.get(nome)]
    unidade = ambiente.get("HOMEDRIVE")
    if unidade:
        raizes += [unidade + "\\Program Files", unidade + "\\Program Files (x86)"]
    return raizes


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
    # O Playwright sincrono exige uma thread sem o loop ativo do Jupyter. A
    # thread e daemon e o chamador so espera o resultado: no Ctrl-C, o controle
    # volta na hora, o navegador e encerrado daqui mesmo (o worker pode estar
    # preso num ``goto``) e o interpretador nao espera o worker para sair.
    sessao = _SessaoLogin()
    resultado: dict[str, Any] = {}

    def trabalhar() -> None:
        try:
            resultado["credencial"] = _obter_credencial(timeout, navegador, sessao)
        # Tudo, inclusive ``SystemExit``: o erro e levantado de novo na thread do chamador.
        except BaseException as exc:  # pylint: disable=broad-except  # noqa: BLE001
            resultado["erro"] = exc

    worker = threading.Thread(target=trabalhar, name="juscraper-govbr", daemon=True)
    worker.start()
    concluiu = False
    try:
        worker.join()
        concluiu = True
    finally:
        if not concluiu:
            sessao.cancelar_e_fechar()
    if "erro" in resultado:
        raise resultado["erro"]
    credencial: CredencialPdpj = resultado["credencial"]
    return credencial


class _SessaoLogin:
    """Estado que o chamador divide com o worker: o pedido de cancelamento e o navegador aberto."""

    def __init__(self) -> None:
        self.cancelar = threading.Event()
        self.processo: subprocess.Popen[bytes] | None = None

    def cancelar_e_fechar(self) -> None:
        self.cancelar.set()
        # So ``terminate``, sem esperar: quem cancela quer o controle de volta ja.
        # Com o navegador fechado, a chamada do Playwright em que o worker estiver
        # falha e o worker termina.
        if self.processo is not None and self.processo.poll() is None:
            self.processo.terminate()


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
    for caminho in caminhos_navegador():
        if Path(caminho).is_file():
            return caminho
    raise RuntimeError(
        "O login pelo gov.br precisa do Google Chrome, Chromium ou Microsoft Edge instalado. "
        "Instale um deles ou informe o executavel em auth_govbr(navegador=...)."
    )


def abrir_navegador(
    executavel: str,
    perfil: Path,
    sessao: _SessaoLogin | None = None,
) -> tuple[subprocess.Popen[bytes], int]:
    """Abre o navegador como processo comum e devolve o processo e a porta CDP.

    ``--remote-debugging-port=0`` deixa o navegador escolher uma porta livre e
    grava-la em ``DevToolsActivePort``, no diretorio do perfil. O perfil
    temporario e obrigatorio: o Chrome recusa a porta de depuracao no perfil
    padrao da pessoa, e o login nao deve se misturar com ele.

    Raises:
        RuntimeError: Quando o navegador fecha, nao publica a porta no prazo
            ou o login e cancelado.
    """
    # Sem ``with``: o processo sobrevive a esta funcao e e encerrado por ``_encerrar``.
    # O executavel vem de ``localizar_navegador`` e a lista vai sem shell.
    processo = subprocess.Popen(  # nosec B603  # pylint: disable=consider-using-with  # noqa: S603
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
    if sessao is not None:
        sessao.processo = processo
    arquivo_porta = perfil / "DevToolsActivePort"
    prazo = time.monotonic() + ESPERA_PELA_PORTA
    while time.monotonic() < prazo:
        if sessao is not None and sessao.cancelar.is_set():
            _encerrar(processo)
            raise RuntimeError("Login no gov.br cancelado.")
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


def _obter_credencial(timeout: float, navegador: str | None, sessao: _SessaoLogin) -> CredencialPdpj:
    # Import tardio: o Playwright e dependencia opcional, do extra ``govbr``.
    try:
        from playwright.sync_api import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            Error as ErroPlaywright,
        )
        from playwright.sync_api import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            TimeoutError as TimeoutPlaywright,
        )
        from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
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
        processo, porta = abrir_navegador(executavel, Path(diretorio), sessao)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
                context = browser.contexts[0]
                captura = _Captura(erros_de_leitura=(ErroPlaywright,))
                context.on("request", captura.ao_requisitar)
                context.on("response", captura.ao_responder)
                page = context.pages[0] if context.pages else context.new_page()
                inicio = time.monotonic()
                _navegar(page, _timeout_de_navegacao(inicio + timeout, inicio), TimeoutPlaywright)
                return _esperar_credencial(page, captura, timeout, sessao.cancelar, ErroPlaywright)
        finally:
            _encerrar(processo)


class _Captura:
    """Guarda o que as escutas do navegador veem.

    Os handlers so enfileiram: ler o corpo de uma resposta dentro do handler
    bloquearia o despacho de eventos do Playwright sincrono. O corpo e lido em
    :meth:`processar`, chamado pelo laco de espera.
    """

    def __init__(self, erros_de_leitura: tuple[type[Exception], ...] = ()) -> None:
        """Cria a captura vazia.

        Args:
            erros_de_leitura: Erros, alem do ``ValueError`` do JSON invalido,
                que a leitura do corpo de uma resposta pode levantar sem que a
                captura deva parar; no login, o ``Error`` do Playwright, para o
                corpo que o navegador ja descartou.
        """
        self.bearer: str | None = None
        self.credencial: CredencialPdpj | None = None
        self._respostas_token: list[Response] = []
        self._erros_de_leitura: tuple[type[Exception], ...] = (ValueError, *erros_de_leitura)

    def ao_requisitar(self, request: Request) -> None:
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

    def ao_responder(self, response: Response) -> None:
        if urlparse(response.url).path.endswith(_CAMINHO_TOKEN) and response.request.method == "POST":
            self._respostas_token.append(response)

    def processar(self) -> None:
        while self._respostas_token:
            dados = _corpo_json(self._respostas_token.pop(0), self._erros_de_leitura)
            access = dados.get("access_token")
            if isinstance(access, str) and access:
                self.credencial = CredencialPdpj(access, dados.get("refresh_token") or None)

    def resultado(self) -> CredencialPdpj | None:
        if self.credencial is not None:
            return self.credencial
        return CredencialPdpj(self.bearer) if self.bearer is not None else None


def _corpo_json(response: Response, erros: tuple[type[Exception], ...]) -> dict[str, Any]:
    """Corpo JSON de uma resposta bem-sucedida; resposta de erro, corpo ilegivel ou nao objeto vira ``{}``."""
    if not response.ok:
        return {}
    try:
        dados = response.json()
    except erros:
        return {}
    return dados if isinstance(dados, dict) else {}


def _navegar(page: Page, timeout_ms: float, tolerado: type[BaseException]) -> None:
    """Abre a consulta do portal, tolerando so os erros da classe ``tolerado``.

    Na abertura, ``tolerado`` e o timeout do Playwright: portal lento nao e erro,
    e o laco espera o token ate o prazo, mas sem rede, DNS ou proxy a falha sobe
    na hora, em vez de virar uma espera do prazo inteiro. No reload, e o
    ``Error`` base do Playwright: a rede acabou de funcionar no caminho ate o
    SSO, e um clique do usuario antes do commit aborta o ``goto`` ("interrupted
    by another navigation", ``net::ERR_ABORTED``) sem que o login tenha falhado;
    a captura continua ouvindo as navegacoes do proprio usuario.
    """
    try:
        page.goto(PORTAL_CONSULTA, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as exc:
        if page.is_closed():
            raise RuntimeError(_JANELA_FECHADA) from exc
        if not isinstance(exc, tolerado):
            raise
        # So a classe: a mensagem do Playwright traz a URL de destino, que depois
        # do SSO pode ser a do portal com o ``code`` de autorizacao no fragmento.
        logger.debug("Navegacao da consulta nao terminou (%s); seguindo a espera.", type(exc).__name__)


def _timeout_de_navegacao(prazo: float, agora: float) -> float:
    """Timeout de um ``goto`` em ms: no maximo 30 s, e nunca alem do prazo do login.

    Enquanto o ``goto`` espera, o laco nao confere cancelamento nem devolve um
    token ja capturado; uma navegacao travada nao pode segurar o laco por minutos.
    """
    return max(min(prazo - agora, TIMEOUT_NAVEGACAO), 1.0) * 1000


@dataclass
class _Espera:
    """Estado do laco de :func:`_esperar_credencial` entre um passo e o seguinte."""

    page: Page
    captura: _Captura
    prazo: float
    erro_no_reload: type[BaseException]
    saiu_do_portal: bool = False
    voltou_em: float | None = None
    recarregou: bool = False
    token_desde: float | None = None

    def credencial_pronta(self, agora: float) -> CredencialPdpj | None:
        """A credencial a devolver neste passo, ou ``None`` para seguir esperando.

        Com refresh token, devolve na hora. So com o access token, espera
        ``ESPERA_PELO_REFRESH`` pela resposta do endpoint de token, que traz
        tambem o refresh. Sem token nenhum, acompanha a navegacao do portal.
        """
        credencial = self.captura.credencial
        if credencial is not None and credencial.refresh_token is not None:
            return credencial
        resultado = self.captura.resultado()
        if resultado is None:
            self._acompanhar_portal(agora)
            return None
        if self.token_desde is None:
            self.token_desde = agora
        return resultado if agora - self.token_desde >= ESPERA_PELO_REFRESH else None

    def _acompanhar_portal(self, agora: float) -> None:
        if urlparse(self.page.url).hostname != _HOST_PORTAL:
            self.saiu_do_portal = True
            return
        if not self.saiu_do_portal or self.recarregou:
            return
        # De volta ao portal depois do login e sem token visto: o reload na
        # /consulta dispara as chamadas autenticadas que expoem o token.
        if self.voltou_em is None:
            self.voltou_em = agora
        if agora - self.voltou_em >= ESPERA_ANTES_DO_RELOAD:
            self.recarregou = True
            _navegar(self.page, _timeout_de_navegacao(self.prazo, agora), self.erro_no_reload)


def _conferir_janela(page: Page, cancelar: threading.Event | None) -> None:
    if cancelar is not None and cancelar.is_set():
        raise RuntimeError("Login no gov.br cancelado.")
    if page.is_closed():
        raise RuntimeError(_JANELA_FECHADA)


def _aguardar(page: Page) -> None:
    try:
        page.wait_for_timeout(500)
    except Exception as exc:  # pylint: disable=broad-except
        if page.is_closed():
            raise RuntimeError(_JANELA_FECHADA) from exc
        raise


def _esperar_credencial(
    page: Page,
    captura: _Captura,
    timeout: float,
    cancelar: threading.Event | None,
    erro_no_reload: type[BaseException],
) -> CredencialPdpj:
    espera = _Espera(page, captura, time.monotonic() + timeout, erro_no_reload)
    while time.monotonic() < espera.prazo:
        _conferir_janela(page, cancelar)
        captura.processar()
        credencial = espera.credencial_pronta(time.monotonic())
        if credencial is not None:
            return credencial
        _aguardar(page)
    raise RuntimeError(
        f"O login no gov.br nao terminou em {timeout:.0f}s ou o portal nao expos o token. "
        "Tente de novo com um timeout maior, ou copie o token do devtools e use auth(token)."
    )
