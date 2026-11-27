"""Guarda: os testes do TJRS sempre limitam as páginas baixadas (#441).

Sem ``paginas`` (ou com ``paginas=None``), ``cjsg`` baixa todas as páginas do
resultado. Em 14/11/2026, "direito civil" tinha 995.956 acórdãos, 10 por
página: o teste ficaria cerca de 30 horas emendando 99.595 requisições, o que
parecia uma conexão presa.
"""
import ast
from pathlib import Path
from typing import TypeGuard

METODOS = {"cjsg", "cjsg_download"}


def _paginas(chamada: ast.Call) -> ast.expr | None:
    if len(chamada.args) >= 2:
        return chamada.args[1]
    return next((kw.value for kw in chamada.keywords if kw.arg == "paginas"), None)


def _baixa_tudo(no: ast.AST) -> TypeGuard[ast.Call]:
    """Chamada a ``cjsg``/``cjsg_download`` sem ``paginas`` ou com ``paginas=None``."""
    if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr in METODOS):
        return False
    paginas = _paginas(no)
    return paginas is None or (isinstance(paginas, ast.Constant) and paginas.value is None)


def test_testes_tjrs_sempre_limitam_paginas():
    faltando = [
        f"{arquivo.name}:{no.lineno}: {ast.unparse(no)}"
        for arquivo in sorted(Path(__file__).parent.glob("test_*.py"))
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8")))
        if _baixa_tudo(no)
    ]
    assert faltando == []
