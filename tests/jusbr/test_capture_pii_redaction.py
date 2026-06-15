"""Regressão: o sanitizador do capture jusbr redige CPF/CNPJ vindo como ``int``.

O PDPJ devolve o CPF ora como string, ora como inteiro cru — e o inteiro perde
os zeros à esquerda. A redação por chave + heurística de dígito verificador só
cobria strings, então um CPF inteiro (em especial o ``numero`` irmão de
``tipo: CPF`` em ``cadastroReceitaFederal``) vazava cru para os samples. Estes
testos travam o gap: ver ``tests/fixtures/capture/jusbr.py``.

CPFs sintéticos: dígito verificador válido, construídos só para teste — não
pertencem a ninguém.
"""
from __future__ import annotations

from fixtures.capture.jusbr import _is_cpf_or_cnpj_value, _redact_value, _walk

_CPF_11_DIGITS = 11144477735      # 11 dígitos, DV válido
_CPF_LEADING_ZERO = 1234567890    # vale 01234567890 após zfill(11)
_NOT_A_CPF = 11144477736          # DV quebrado de propósito


def test_is_cpf_or_cnpj_value_accepts_int_cpf() -> None:
    assert _is_cpf_or_cnpj_value(_CPF_11_DIGITS) is True
    # CPF começando com 0 chega como int de 10 dígitos; zfill resgata.
    assert _is_cpf_or_cnpj_value(_CPF_LEADING_ZERO) is True


def test_is_cpf_or_cnpj_value_rejects_plain_ids_and_bools() -> None:
    assert _is_cpf_or_cnpj_value(_NOT_A_CPF) is False
    assert _is_cpf_or_cnpj_value(0) is False
    assert _is_cpf_or_cnpj_value(True) is False  # bool é subclasse de int, mas não é documento
    assert _is_cpf_or_cnpj_value("nao-e-cpf") is False


def test_walk_redacts_int_cpf_anywhere() -> None:
    out = _walk({"qualquerChave": _CPF_11_DIGITS}, {})
    assert out["qualquerChave"] == "REDACTED"


def test_walk_redacts_numero_sibling_of_tipo_cpf() -> None:
    # Shape real do PDPJ: cadastroReceitaFederal: {"tipo": "CPF", "numero": <int>}.
    assert _walk({"tipo": "CPF", "numero": _CPF_11_DIGITS}, {})["numero"] == "REDACTED"
    # Força a redação mesmo quando o número não passa pelo DV (defesa em profundidade).
    assert _walk({"tipo": "CPF", "numero": _NOT_A_CPF}, {})["numero"] == "REDACTED"


def test_walk_preserves_plain_numeric_ids() -> None:
    # Sem ``tipo: CPF`` e sem DV válido, um ID numérico comum não é tocado.
    out = _walk({"idCodex": _NOT_A_CPF, "total": 42}, {})
    assert out["idCodex"] == _NOT_A_CPF
    assert out["total"] == 42


def test_walk_still_redacts_string_cpf() -> None:
    # Comportamento pré-existente (CPF como string de 11 dígitos) preservado.
    assert _walk({"campo": "11144477735"}, {})["campo"] == "REDACTED"
    assert _redact_value("documento", "11144477735", {}) == "REDACTED"
