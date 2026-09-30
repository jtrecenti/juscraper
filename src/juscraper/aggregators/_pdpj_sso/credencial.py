"""Credencial do SSO do PJe e leitura da validade dos JWTs."""
from __future__ import annotations

import time
from dataclasses import dataclass

import jwt

# Folga antes do ``exp``: um token que vence durante a requisicao chegaria
# vencido ao servidor, entao a renovacao acontece um pouco antes.
MARGEM_RENOVACAO = 30.0


@dataclass
class CredencialPdpj:
    """Par de tokens emitido pelo SSO do PJe.

    ``refresh_token`` fica ``None`` quando o access token veio de fora do
    fluxo OAuth (variavel de ambiente, ``auth(token)``, cabecalho capturado
    sem a resposta do endpoint de token).
    """

    access_token: str
    refresh_token: str | None = None


def ler_exp(token: str) -> float | None:
    """Devolve o claim ``exp`` do JWT, ou ``None`` quando ele nao existe.

    Raises:
        jwt.InvalidTokenError: Quando ``token`` nao e um JWT estrutural.
    """
    claims = jwt.decode(
        token,
        options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
        algorithms=["RS256", "HS256", "ES256", "none"],
    )
    exp = claims.get("exp")
    return float(exp) if isinstance(exp, (int, float)) else None


def vigente(token: str, margem: float = 0.0) -> bool:
    """Diz se o token ainda vale por mais ``margem`` segundos.

    Token sem ``exp`` conta como vigente, como no ``auth()`` dos scrapers.
    Token que nao e JWT tambem: o refresh token do Keycloak costuma ser JWT,
    mas se deixar de ser, quem decide a validade e o SSO ao receber o POST.
    """
    try:
        exp = ler_exp(token)
    except jwt.InvalidTokenError:
        return True
    return exp is None or exp - margem > time.time()


def utilizavel(credencial: CredencialPdpj) -> bool:
    """Diz se a credencial ainda serve sem novo login.

    Serve quando o access token e JWT e vale agora, ou quando ha refresh token
    vigente para renova-lo na primeira requisicao.
    """
    try:
        ler_exp(credencial.access_token)
    except jwt.InvalidTokenError:
        return False
    if vigente(credencial.access_token):
        return True
    return credencial.refresh_token is not None and vigente(credencial.refresh_token)
