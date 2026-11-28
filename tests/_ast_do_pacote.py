"""Andaime dos testes estruturais que leem o código de ``src/juscraper`` pela AST.

Os testes que varrem o pacote (``test_notimplemented_so_em_stub.py``,
``test_docs_interlinks.py``) precisam das mesmas duas coisas: os arquivos do
pacote, com o caminho relativo que vai na mensagem, e cada nó com o nome
qualificado do escopo em que está.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

RAIZ_PACOTE = Path(__file__).resolve().parents[1] / "src" / "juscraper"

Funcao = ast.FunctionDef | ast.AsyncFunctionDef
MODULO = "<módulo>"


def arquivos_do_pacote() -> Iterator[tuple[Path, str]]:
    """``(arquivo, caminho relativo a src/juscraper)`` de cada ``.py`` do pacote, em ordem."""
    for arquivo in sorted(RAIZ_PACOTE.rglob("*.py")):
        yield arquivo, arquivo.relative_to(RAIZ_PACOTE).as_posix()


def nos_com_escopo(arvore: ast.AST) -> Iterator[tuple[str, ast.AST, Funcao | None]]:
    """Cada nó de ``arvore`` com o nome qualificado do escopo e a função mais interna que o contém.

    O nome junta as classes e funções que envolvem o nó (``"C.m"``), ou é
    ``"<módulo>"`` fora delas. A definição de classe ou função sai com o nome
    de quem a contém, e o corpo dela, com o nome dela.
    """

    def visitar(
        no: ast.AST, nomes: tuple[str, ...], funcao: Funcao | None
    ) -> Iterator[tuple[str, ast.AST, Funcao | None]]:
        for filho in ast.iter_child_nodes(no):
            yield ".".join(nomes) or MODULO, filho, funcao
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from visitar(filho, (*nomes, filho.name), filho)
            elif isinstance(filho, ast.ClassDef):
                yield from visitar(filho, (*nomes, filho.name), funcao)
            else:
                yield from visitar(filho, nomes, funcao)

    yield from visitar(arvore, (), None)


def nome_qualificado(escopo: str, definicao: Funcao | ast.ClassDef) -> str:
    """O nome qualificado de ``definicao``, achada por :func:`nos_com_escopo` em ``escopo``."""
    return definicao.name if escopo == MODULO else f"{escopo}.{definicao.name}"
