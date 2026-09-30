"""Renovacao do access token pelo refresh token do SSO do PJe."""
from __future__ import annotations

from collections.abc import Callable

import requests

from .credencial import MARGEM_RENOVACAO, CredencialPdpj, vigente

TOKEN_URL = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"  # nosec B105
# Cliente publico do portal de servicos: o Keycloak nao exige segredo na troca.
CLIENT_ID = "portalexterno-frontend"


def renovar(refresh_token: str, timeout: float = 30.0) -> CredencialPdpj:
    """Troca o refresh token por um access token novo.

    Usa ``requests.post`` avulso, fora da sessao do scraper: a sessao tem
    :class:`AuthPdpj` em ``session.auth``, que chamaria a renovacao de novo.

    Raises:
        RuntimeError: Quando o SSO recusa o refresh token ou responde sem
            ``access_token``.
    """
    resposta = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": CLIENT_ID},
        timeout=timeout,
    )
    try:
        dados = resposta.json() if resposta.ok else {}
    except ValueError:
        dados = {}
    access = dados.get("access_token") if isinstance(dados, dict) else None
    if not isinstance(access, str) or not access:
        raise RuntimeError(
            f"O SSO do PJe recusou a renovacao do token (HTTP {resposta.status_code}). "
            "A sessao expirou: chame auth_govbr() de novo."
        )
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
    ) -> None:
        self.credencial = credencial
        self.ao_renovar = ao_renovar

    def __call__(self, requisicao: requests.PreparedRequest) -> requests.PreparedRequest:
        refresh = self.credencial.refresh_token
        if refresh is not None and not vigente(self.credencial.access_token, MARGEM_RENOVACAO):
            self.credencial = renovar(refresh)
            if self.ao_renovar is not None:
                self.ao_renovar(self.credencial)
        requisicao.headers["Authorization"] = f"Bearer {self.credencial.access_token}"
        return requisicao
