"""``raise NotImplementedError`` só em stub: função cujo corpo é a docstring e o raise.

Filtro que o backend não oferece sai do schema pydantic do endpoint, e o
``extra="forbid"`` o recusa com ``TypeError`` na API pública (CONTRIBUTING >
Schemas pydantic). Um ``NotImplementedError`` levantado no meio do downloader
quebra esse contrato de dois jeitos: quem consome a API, como o helper dos
testes de release, só reconhece filtro recusado por ``TypeError``; e
``tests/schemas/test_schema_coverage.py`` trata como stub todo método cujo
código contém ``raise NotImplementedError``, então um endpoint implementado
com esse raise num ramo sai do registro de schemas sem aviso.

Stub de endpoint (``cpopg``/``cposg`` não implementados) e método abstrato
sobrescrito pelas subclasses continuam com ``NotImplementedError``.
"""

import ast
from pathlib import Path
from typing import TypeGuard

import pytest

RAIZ_PACOTE = Path(__file__).resolve().parents[1] / "src" / "juscraper"

# (caminho relativo a src/juscraper, nome qualificado da função) -> motivo.
EXCECOES = {
    ("courts/_esaj/base.py", "EsajSearchScraper.__init__"): (
        "subclasse eSAJ sem BASE_URL é erro de quem escreve o raspador, não filtro do usuário"
    ),
}


def _levanta_not_implemented(no: ast.AST) -> TypeGuard[ast.Raise]:
    if not isinstance(no, ast.Raise):
        return False
    alvo = no.exc.func if isinstance(no.exc, ast.Call) else no.exc
    return isinstance(alvo, ast.Name) and alvo.id == "NotImplementedError"


def _e_stub(funcao: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    corpo = funcao.body
    if isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
        corpo = corpo[1:]
    return len(corpo) == 1 and _levanta_not_implemented(corpo[0])


def raises_fora_de_stub(codigo: str) -> list[tuple[int, str]]:
    """Lista ``(linha, função)`` de cada ``raise NotImplementedError`` fora de stub.

    A função é a mais interna que contém o raise, com o nome qualificado pelas
    classes e funções que a envolvem; raise fora de função sai como
    ``<módulo>``.
    """
    achados: list[tuple[int, str]] = []

    def visitar(no: ast.AST, nomes: tuple[str, ...], funcao: ast.FunctionDef | ast.AsyncFunctionDef | None) -> None:
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visitar(filho, (*nomes, filho.name), filho)
            elif isinstance(filho, ast.ClassDef):
                visitar(filho, (*nomes, filho.name), funcao)
            else:
                if _levanta_not_implemented(filho) and not (funcao is not None and _e_stub(funcao)):
                    achados.append((filho.lineno, ".".join(nomes) or "<módulo>"))
                visitar(filho, nomes, funcao)

    visitar(ast.parse(codigo), (), None)
    return achados


def _achados_do_pacote() -> dict[tuple[str, str], int]:
    achados: dict[tuple[str, str], int] = {}
    for arquivo in sorted(RAIZ_PACOTE.rglob("*.py")):
        caminho = arquivo.relative_to(RAIZ_PACOTE).as_posix()
        for linha, funcao in raises_fora_de_stub(arquivo.read_text(encoding="utf-8")):
            achados.setdefault((caminho, funcao), linha)
    return achados


def test_not_implemented_so_em_stub_no_pacote():
    violacoes = [
        f"src/juscraper/{caminho}:{linha} em {funcao}"
        for (caminho, funcao), linha in _achados_do_pacote().items()
        if (caminho, funcao) not in EXCECOES
    ]
    assert violacoes == [], (
        "raise NotImplementedError fora de stub; filtro não suportado sai do schema "
        "pydantic e cai no extra='forbid' (TypeError):\n" + "\n".join(violacoes)
    )


def test_excecoes_ainda_existem():
    assert set(EXCECOES) <= set(_achados_do_pacote())


@pytest.mark.parametrize(
    "codigo",
    [
        "def f(x):\n    if x:\n        raise NotImplementedError('filtro x')\n    return 1\n",
        "def f(x):\n    '''Doc.'''\n    y = 1\n    raise NotImplementedError\n",
        (
            "class C:\n    def m(self):\n        def g(x):\n"
            "            if x:\n                raise NotImplementedError()\n        return g\n"
        ),
        "async def f():\n    if True:\n        raise NotImplementedError('x')\n    return 1\n",
        "raise NotImplementedError\n",
    ],
    ids=["ramo-de-filtro", "corpo-com-mais-codigo", "funcao-aninhada", "async", "modulo"],
)
def test_raise_fora_de_stub_e_reprovado(codigo):
    assert raises_fora_de_stub(codigo)


@pytest.mark.parametrize(
    "codigo",
    [
        "def cposg(self, id_cnj):\n    '''Stub.'''\n    raise NotImplementedError('não implementado')\n",
        "def auth(self, token):  # pragma: no cover\n    raise NotImplementedError\n",
        "class C:\n    async def m(self):\n        '''Doc.'''\n        raise NotImplementedError()\n",
        "def f(x):\n    raise ValueError('x')\n",
    ],
    ids=["stub-com-docstring", "stub-sem-docstring", "metodo-async-stub", "outra-excecao"],
)
def test_stub_e_outras_excecoes_passam(codigo):
    assert raises_fora_de_stub(codigo) == []


def test_nome_qualificado_aponta_a_funcao_mais_interna():
    codigo = "class C:\n    def m(self):\n        if self:\n            raise NotImplementedError\n        return 1\n"
    assert raises_fora_de_stub(codigo) == [(4, "C.m")]
