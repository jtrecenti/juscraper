"""JWTs de teste para o SSO do PDPJ."""
import time

import jwt

# Chave de 32+ bytes: o PyJWT avisa com chave HMAC curta e o pytest trata aviso como erro.
_CHAVE = "0123456789abcdef0123456789abcdef-test"


def token(exp_em: float | None = 3600.0, **claims) -> str:
    """JWT HS256 que vence ``exp_em`` segundos a partir de agora (``None`` = sem ``exp``)."""
    if exp_em is not None:
        claims["exp"] = int(time.time() + exp_em)
    codificado: str = jwt.encode(claims, _CHAVE, algorithm="HS256")
    return codificado
