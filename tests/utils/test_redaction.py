"""Testes para ``juscraper.utils.logging_cfg.redact_headers``.

Garante que o helper de redacao mascara credenciais (Authorization, Cookie,
etc.) antes de irem para log, sem mutar o dict original (hardening #270).
"""
from juscraper.utils.logging_cfg import redact_headers


def test_redige_authorization_case_insensitive():
    assert redact_headers({"Authorization": "Bearer xyz"}) == {
        "Authorization": "[REDACTED]"
    }
    assert redact_headers({"authorization": "Bearer xyz"}) == {
        "authorization": "[REDACTED]"
    }


def test_preserva_headers_nao_sensiveis():
    out = redact_headers({"authorization": "Bearer xyz", "accept": "*/*"})
    assert out == {"authorization": "[REDACTED]", "accept": "*/*"}


def test_redige_cookie_set_cookie_e_api_keys():
    out = redact_headers({
        "Cookie": "session=abc",
        "Set-Cookie": "session=abc; HttpOnly",
        "X-API-Key": "k1",
        "api-key": "k2",
    })
    assert out == {
        "Cookie": "[REDACTED]",
        "Set-Cookie": "[REDACTED]",
        "X-API-Key": "[REDACTED]",
        "api-key": "[REDACTED]",
    }


def test_nao_muta_o_dict_original():
    original = {"authorization": "Bearer xyz", "accept": "*/*"}
    redact_headers(original)
    assert original == {"authorization": "Bearer xyz", "accept": "*/*"}


def test_mapping_vazio():
    assert redact_headers({}) == {}
