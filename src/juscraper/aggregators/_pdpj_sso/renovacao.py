"""Renovacao do access token pelo refresh token do SSO do PJe."""
from __future__ import annotations

from collections.abc import Callable

import jwt
import requests

from ...core.failures import resumir_falhas
from .credencial import MARGEM_RENOVACAO, CredencialPdpj, ler_exp, vigente

TOKEN_URL = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"  # nosec B105
# Cliente publico do portal de servicos: o Keycloak nao exige segredo na troca.
CLIENT_ID = "portalexterno-frontend"


class ErroSsoPdpj(RuntimeError):
    """Falha ao renovar o token no SSO do PJe.

    Nao herda de ``requests.RequestException`` de proposito: os downloads dos
    scrapers tratam essas excecoes como falha do documento ou do processo, e uma
    falha do SSO viraria texto ``None`` ou "processo nao encontrado" em silencio.
    """


def anotar_falhas_antes_do_sso(erro: ErroSsoPdpj, falhas: list[str], descricao: str) -> None:
    """Anexa ao erro do SSO as falhas do lote que vieram antes dele.

    Mesmo tratamento que ``anotar_falhas_anteriores`` (``juscraper.core.failures``)
    da ao 401: a falha do SSO tambem interrompe o lote, e as falhas anteriores
    vao numa nota do erro, e nao num aviso.
    """
    if falhas:
        erro.add_note(f"Antes da falha do SSO, {resumir_falhas(falhas, descricao)}")


class RenovacaoPdpjError(ErroSsoPdpj):
    """O SSO recusou a renovacao: a sessao acabou e so um novo login resolve."""


class SsoPdpjIndisponivelError(ErroSsoPdpj):
    """O SSO nao respondeu ou respondeu com erro transitorio; tentar de novo pode resolver."""


# Status com que o Keycloak recusa um refresh token vencido, revogado ou
# desconhecido (``invalid_grant``). Qualquer outro erro e tratado como
# transitorio e a proxima requisicao tenta de novo.
_STATUS_RECUSA = frozenset({400, 401})
_MENSAGEM_RECUSA = "O SSO do PJe recusou a renovacao do token. A sessao expirou: chame auth_govbr() de novo."


def renovar(refresh_token: str, timeout: float = 30.0) -> CredencialPdpj:
    """Troca o refresh token por um access token novo.

    Usa ``requests.post`` avulso, fora da sessao do scraper: a sessao tem
    :class:`AuthPdpj` em ``session.auth``, que chamaria a renovacao de novo.

    Raises:
        RenovacaoPdpjError: Quando o SSO recusa o refresh token (HTTP 400 ou
            401) ou responde 2xx sem ``access_token``.
        SsoPdpjIndisponivelError: Em erro de rede ou outro erro HTTP do SSO
            (503, 429...), que e transitorio.
    """
    try:
        resposta = requests.post(
            TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": CLIENT_ID},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise SsoPdpjIndisponivelError(
            f"O SSO do PJe nao respondeu ao renovar o token ({type(exc).__name__}); tente de novo."
        ) from exc
    if resposta.status_code in _STATUS_RECUSA:
        raise RenovacaoPdpjError(f"{_MENSAGEM_RECUSA} (HTTP {resposta.status_code})")
    if not resposta.ok:
        raise SsoPdpjIndisponivelError(
            f"O SSO do PJe respondeu HTTP {resposta.status_code} ao renovar o token; tente de novo."
        )
    try:
        dados = resposta.json()
    except ValueError:
        dados = {}
    access = dados.get("access_token") if isinstance(dados, dict) else None
    if not isinstance(access, str) or not access:
        raise RenovacaoPdpjError(f"{_MENSAGEM_RECUSA} (resposta sem access_token)")
    # O Keycloak pode rotacionar o refresh token; sem um novo, o antigo segue valendo.
    return CredencialPdpj(access, dados.get("refresh_token") or refresh_token)


class AuthPdpj(requests.auth.AuthBase):
    """Poe o ``Authorization`` em cada requisicao e renova o token antes de vencer.

    Fica em ``session.auth``. O ``requests`` aplica o ``auth`` depois de mesclar
    os cabecalhos da sessao e da chamada, entao o valor posto aqui vence o
    cabecalho fixo da sessao e o ``authorization`` explicito que o JusBR passa
    ao baixar texto de documento. Isso cobre todo HTTP dos scrapers, inclusive
    os lacos longos de download, sem checagem de validade em cada metodo.
    """

    def __init__(
        self,
        credencial: CredencialPdpj,
        ao_renovar: Callable[[CredencialPdpj], None] | None = None,
        ler_cache: Callable[[], CredencialPdpj | None] | None = None,
    ) -> None:
        self.credencial = credencial
        self.ao_renovar = ao_renovar
        self.ler_cache = ler_cache
        # Refresh tokens que o SSO ja recusou: nao voltam a ser enviados, e a
        # requisicao seguinte levanta sem novo POST. Guardar o token, e nao a
        # falha, deixa um refresh novo gravado no cache por outra instancia ser
        # tentado.
        self._recusados: set[str] = set()
        self._ultima_recusa = _MENSAGEM_RECUSA

    def __call__(self, requisicao: requests.PreparedRequest) -> requests.PreparedRequest:
        """Poe o access token na requisicao, renovando-o antes se estiver para vencer."""
        if self.credencial.refresh_token is not None and not vigente(self.credencial.access_token, MARGEM_RENOVACAO):
            self._renovar()
        requisicao.headers["Authorization"] = f"Bearer {self.credencial.access_token}"
        return requisicao

    def _renovar(self) -> None:
        do_cache = self.ler_cache() if self.ler_cache is not None else None
        if do_cache is not None and do_cache.access_token != self.credencial.access_token and _access_vigente(
            do_cache.access_token
        ):
            # Outra instancia (JusBR e PDPJ no mesmo notebook, ou outro processo)
            # ja renovou ou refez o login e gravou o cache. Sem refresh no cache,
            # o proprio segue guardado para quando o access adotado vencer.
            self._trocar(CredencialPdpj(do_cache.access_token, do_cache.refresh_token or self.credencial.refresh_token))
            return
        # O refresh do cache vem primeiro porque o desta instancia pode ter sido
        # rotacionado e revogado; se o SSO recusar o do cache, o proprio ainda e
        # tentado.
        candidatos = [do_cache.refresh_token if do_cache is not None else None, self.credencial.refresh_token]
        for refresh in dict.fromkeys(r for r in candidatos if r is not None and r not in self._recusados):
            try:
                nova = renovar(refresh)
            except RenovacaoPdpjError as exc:
                self._recusados.add(refresh)
                self._ultima_recusa = str(exc)
                continue
            self._trocar(nova)
            return
        # Excecao nova a cada chamada: relevantar sempre o mesmo objeto faria o
        # traceback crescer a cada requisicao de quem captura e segue o laco.
        raise RenovacaoPdpjError(self._ultima_recusa)

    def _trocar(self, nova: CredencialPdpj) -> None:
        self.credencial = nova
        if self.ao_renovar is not None:
            self.ao_renovar(nova)


def _access_vigente(token: str) -> bool:
    """Access token que e JWT e ainda vale alem da margem; lixo no cache nao conta."""
    try:
        ler_exp(token)
    except jwt.InvalidTokenError:
        return False
    return vigente(token, MARGEM_RENOVACAO)
