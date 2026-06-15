"""Offline contract tests for JusbrScraper.auth.

``auth(token)`` apenas decodifica o JWT (sem verificar assinatura) e seta o
header ``Authorization: Bearer <token>`` na sessao quando o token e valido.
Nao dispara nenhuma request HTTP, entao os testes aqui nao usam ``responses``.

``verify_exp=True`` foi tornado explicito no ``client.py`` (followup 1 da
#141): com ``verify_signature=False`` o PyJWT desativa ``verify_exp`` por
padrao e o ramo ``except jwt.ExpiredSignatureError`` virava dead code. Agora
tokens expirados levantam ``ValueError("Token JWT expirado.")`` como
documentado.
"""
import jwt
import pytest

import juscraper as jus

# PyJWT emite ``InsecureKeyLengthWarning`` para chaves HMAC < 32 bytes em SHA256;
# o ``filterwarnings = ["error"]`` do pytest converte isso em falha. Chave de 32+
# bytes evita ruido sem afetar o contrato (auth nao verifica assinatura).
_HMAC_KEY = "0123456789abcdef0123456789abcdef-test"


def _token(claims: dict) -> str:
    """Build a structurally valid JWT with the given claims (HS256)."""
    encoded: str = jwt.encode(claims, _HMAC_KEY, algorithm="HS256")
    return encoded


def test_auth_token_valido_seta_header():
    scraper = jus.scraper("jusbr")
    token = _token({"sub": "tester", "exp": 9999999999})

    assert scraper.auth(token) is True
    assert scraper.session.headers["authorization"] == f"Bearer {token}"
    assert scraper.token == token


def test_auth_token_expirado_levanta_value_error():
    """Token com ``exp`` no passado levanta ``ValueError("Token JWT expirado.")``.

    Garantido pelo ``"verify_exp": True`` explicito nas options do
    ``jwt.decode`` em ``client.py:auth`` (followup 1 da #141).
    """
    scraper = jus.scraper("jusbr")
    expired = _token({"sub": "tester", "exp": 0})

    with pytest.raises(ValueError, match="expirado"):
        scraper.auth(expired)
    assert "authorization" not in scraper.session.headers
    assert scraper.token is None


def test_auth_token_sem_exp_passa_silencioso():
    """Token sem claim ``exp`` e aceito sem erro (PyJWT so valida quando o
    claim existe). Header e setado e ``auth`` retorna ``True``.
    """
    scraper = jus.scraper("jusbr")
    no_exp = _token({"sub": "tester"})

    assert scraper.auth(no_exp) is True
    assert scraper.session.headers["authorization"] == f"Bearer {no_exp}"


def test_auth_token_malformado_levanta_value_error():
    """String que nao e JWT estrutural cai em ``InvalidTokenError`` no
    ``jwt.decode`` — o ``except`` re-levanta como ``ValueError``.
    """
    scraper = jus.scraper("jusbr")

    with pytest.raises(ValueError, match="inv[áa]lido"):
        scraper.auth("not-a-jwt")
    assert "authorization" not in scraper.session.headers
    assert scraper.token is None
