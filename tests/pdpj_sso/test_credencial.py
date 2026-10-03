"""Validade dos tokens da credencial do PDPJ."""
import pytest

from juscraper.aggregators._pdpj_sso.credencial import MARGEM_RENOVACAO, vigente
from tests.pdpj_sso._jwt import token


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (token(3600), True),
        (token(-60), False),
        (token(None), True),
        # Refresh token que deixou de ser JWT: quem decide a validade é o SSO.
        ("refresh-opaco", True),
    ],
    ids=["futuro", "vencido", "sem-exp", "nao-jwt"],
)
def test_vigente(valor, esperado):
    assert vigente(valor) is esperado


def test_vigente_desconta_a_margem():
    quase_vencendo = token(MARGEM_RENOVACAO / 2)
    assert vigente(quase_vencendo)
    assert not vigente(quase_vencendo, MARGEM_RENOVACAO)
