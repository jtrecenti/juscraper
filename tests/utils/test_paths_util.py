"""Testes do util ``safe_path_component`` (refs #269)."""
from __future__ import annotations

import pytest

from juscraper.utils import safe_path_component


@pytest.mark.parametrize(
    "value, expected",
    [
        ("12345", "12345"),
        ("1H0ABC0000", "1H0ABC0000"),
        ("abc.def", "abc.def"),
        ("a-b_c.1", "a-b_c.1"),
        ("...", "..."),  # nao e "." nem ".." — fica no diretorio, inofensivo
        (12345, "12345"),  # coercao para str
    ],
)
def test_aceita_identificadores_validos(value, expected):
    assert safe_path_component(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "../etc/passwd",
        "a/b",
        "a\\b",
        "..",
        ".",
        "",
        "/abs",
        "a/../b",
        "foo bar",  # espaco nao e permitido
        "evil\x00",  # byte nulo
    ],
)
def test_rejeita_traversal_e_separadores(value):
    with pytest.raises(ValueError):
        safe_path_component(value)


def test_mensagem_inclui_field():
    with pytest.raises(ValueError, match="cdProcesso"):
        safe_path_component("../x", field="cdProcesso")
