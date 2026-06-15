"""Testes de hardening de logging no ``auth`` do JusBR (#270).

Garante que, mesmo com ``verbose=2`` (DEBUG), os valores dos claims do JWT
nao aparecem no log -- apenas a contagem de claims.
"""
import logging

import jwt

import juscraper as jus


def test_auth_nao_loga_valores_dos_claims(caplog):
    token = jwt.encode(
        {"sub": "usuario-secreto-123", "email": "vazou@example.com"},
        "x" * 32,
        algorithm="HS256",
    )
    scraper = jus.scraper("jusbr", verbose=2)
    with caplog.at_level(logging.DEBUG, logger="juscraper.aggregators.jusbr.client"):
        assert scraper.auth(token) is True
    assert "usuario-secreto-123" not in caplog.text
    assert "vazou@example.com" not in caplog.text
    assert "claims" in caplog.text
