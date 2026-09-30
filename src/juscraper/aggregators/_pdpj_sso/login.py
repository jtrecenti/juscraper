"""Login no gov.br num Chromium com janela, para capturar o token do PDPJ.

O login do SSO do PJe passa pelo gov.br, que pede captcha e segundo fator,
entao a pessoa faz o login na janela e o codigo so observa o trafego. Duas
escutas capturam o token: a resposta do endpoint de token do SSO, que traz
access e refresh token, e, como reserva, o cabecalho ``Authorization`` das
chamadas do portal a ``*.pdpj.jus.br``, que traz so o access token.

O navegador abre sem ``user_agent`` proprio: com janela, o Chromium ja se
anuncia como Chrome comum, e trocar so o user agent o deixaria em desacordo
com os client hints que ele envia.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

from .credencial import CredencialPdpj

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


def obter_credencial_govbr(timeout: float = 300.0) -> CredencialPdpj:
    """Abre o portal de servicos do PDPJ, espera o login e devolve a credencial.

    Args:
        timeout (float): Segundos para a pessoa concluir o login. Default ``300``.

    Returns:
        CredencialPdpj: Access token e, quando o SSO o entrega ao navegador,
        refresh token.

    Raises:
        ImportError: Quando o Playwright nao esta instalado (extra ``juscraper[govbr]``).
        RuntimeError: Quando a janela e fechada ou o prazo acaba sem token.
    """
    # O Playwright sincrono exige uma thread sem o loop ativo do Jupyter.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_obter_credencial, timeout).result()


def _obter_credencial(timeout: float) -> CredencialPdpj:
    try:
        from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "O login pelo gov.br precisa do Playwright. Instale com "
            "`pip install 'juscraper[govbr]'` seguido de `playwright install chromium`, "
            "ou passe um token ja obtido em `auth(token)` ou na variavel PDPJ_JWT."
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            context = browser.new_context(locale="pt-BR")
            captura = _Captura()
            context.on("request", captura.ao_requisitar)
            context.on("response", captura.ao_responder)
            page = context.new_page()
            page.goto(PORTAL_CONSULTA, wait_until="domcontentloaded", timeout=timeout * 1000)
            return _esperar_credencial(page, captura, timeout)
        finally:
            browser.close()


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
        if valor.lower().startswith("bearer ") and valor[7:].strip():
            self.bearer = valor[7:].strip()

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


def _esperar_credencial(page: Any, captura: _Captura, timeout: float) -> CredencialPdpj:
    prazo = time.monotonic() + timeout
    saiu_do_portal = False
    voltou_em: float | None = None
    recarregou = False
    token_desde: float | None = None
    while time.monotonic() < prazo:
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
                page.goto(PORTAL_CONSULTA, wait_until="domcontentloaded")
                recarregou = True
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
