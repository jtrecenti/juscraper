"""Testes de hardening de logging no ``auth`` do PDPJ (#270).

Garante que o ``sub`` do JWT nao aparece no log de INFO emitido com
``verbose=1``.
"""
import logging

import jwt

import juscraper as jus


def test_auth_nao_loga_sub(caplog):
    token = jwt.encode({"sub": "usuario-secreto-123"}, "x" * 32, algorithm="HS256")
    scraper = jus.scraper("pdpj", verbose=1)
    with caplog.at_level(logging.INFO, logger="juscraper.aggregators.pdpj.client"):
        assert scraper.auth(token) is True
    assert "usuario-secreto-123" not in caplog.text
    assert "token JWT aceito" in caplog.text
