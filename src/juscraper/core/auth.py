"""Validação local de JWT, compartilhada pelos agregadores autenticados por token.

JusBR e PDPJ recebem o mesmo JWT do SSO do PJe e o validam antes de usá-lo. A
validação mora aqui para os dois ``auth()`` não divergirem: uma cópia do
bloco que perdeu ``verify_exp`` já deixou um deles aceitando token vencido.
"""
from __future__ import annotations

from typing import Any

import jwt


def validar_jwt(token: str) -> dict[str, Any]:
    """Decodifica ``token`` sem verificar a assinatura e confere a expiração.

    A assinatura não é verificada porque a chave pública do emissor não está
    disponível ao cliente; a decodificação serve para recusar cedo o token
    malformado ou vencido. ``verify_exp`` precisa ser explícito: com
    ``verify_signature=False`` o PyJWT desliga também a verificação de ``exp``.
    Token sem o claim ``exp`` é aceito, porque o PyJWT só confere o claim que
    existe.

    O helper não tem efeito colateral. O ``auth()`` que o chama só troca o
    token e o header da sessão depois que ele volta, e por isso um ``auth()``
    que falha mantém o token anterior válido.

    Args:
        token: O JWT, sem o prefixo ``Bearer``.

    Returns:
        Os claims do token.

    Raises:
        ValueError: ``"Token JWT expirado."`` quando ``exp`` já passou, ou
            ``"Token JWT inválido: ..."`` quando o token é malformado.
    """
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False, "verify_exp": True},
            algorithms=["RS256", "HS256", "ES256", "none"],
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Token JWT expirado.") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Token JWT inválido: {exc}") from exc
    return claims
