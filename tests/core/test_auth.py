"""Testes de ``juscraper.core.auth.validar_jwt``, usado pelo ``auth()`` do JusBR e do PDPJ."""
from __future__ import annotations

import jwt
import pytest

from juscraper.core.auth import validar_jwt

# Chave HMAC de 32+ bytes: abaixo disso o PyJWT emite InsecureKeyLengthWarning,
# que o ``filterwarnings = ["error"]`` converte em falha. A assinatura não é verificada.
_HMAC_KEY = "0123456789abcdef0123456789abcdef-test"


def test_devolve_os_claims():
    token = jwt.encode({"sub": "tester", "exp": 9999999999}, _HMAC_KEY, algorithm="HS256")

    assert validar_jwt(token) == {"sub": "tester", "exp": 9999999999}


def test_token_vencido():
    token = jwt.encode({"sub": "tester", "exp": 0}, _HMAC_KEY, algorithm="HS256")

    with pytest.raises(ValueError, match=r"^Token JWT expirado\.$") as erro:
        validar_jwt(token)
    assert isinstance(erro.value.__cause__, jwt.ExpiredSignatureError)


def test_token_malformado():
    with pytest.raises(ValueError, match=r"^Token JWT inválido: ") as erro:
        validar_jwt("not-a-jwt")
    assert isinstance(erro.value.__cause__, jwt.InvalidTokenError)


def test_token_sem_exp_e_aceito():
    token = jwt.encode({"sub": "tester"}, _HMAC_KEY, algorithm="HS256")

    assert validar_jwt(token) == {"sub": "tester"}


def test_assinatura_nao_e_verificada():
    token = jwt.encode({"sub": "tester"}, "outra-chave-de-32-bytes-ou-mais-aqui", algorithm="HS256")

    assert validar_jwt(token)["sub"] == "tester"
