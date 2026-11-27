"""A seleção ``paginas`` só é lida pelos helpers de ``utils/pagination.py``.

Cada raspador que cortava a seleção ao total à mão divergia dos demais: o
ComunicaCNJ ignorava o passo do ``range``, o Falcão baixava duas vezes a página
repetida, o TJAP e o TJRS pediam a página além do total, e nenhum avisava das
páginas de fora (#789, #794). O contrato comum (página repetida uma vez só,
página além do total no log do tribunal, ``range`` sem ser percorrido, passo
respeitado) mora nos helpers: :func:`paginas_no_intervalo`,
:func:`baixar_paginas_pedidas`, :func:`menor_pagina`, :func:`maior_pagina` e
:func:`paginas_unicas` (CONTRIBUTING > Seleção de páginas).

O teste reprova, fora de ``utils/pagination.py`` e da normalização
(``utils/params.py``, ``schemas/mixins.py``), o código que lê a seleção à mão:
``.start``/``.stop``/``.step``, índice, ``isinstance(..., range)``,
``max``/``min``/``list``/``sorted``/``set``/``tuple``, laço direto sobre ela ou
por ``tqdm``/``enumerate``/``iter``/``reversed`` e ``[*paginas]``.
A seleção é reconhecida pelo nome: ``paginas``, ``paginas_norm`` e o atributo
``paginas_normalizadas``. Variável ``paginas`` com outro conteúdo (páginas já
baixadas) entra em :data:`EXCECOES`, com o motivo.
"""

import ast
from pathlib import Path

import pytest

RAIZ_PACOTE = Path(__file__).resolve().parents[1] / "src" / "juscraper"

# Onde a seleção é normalizada ou lida pelos helpers.
ARQUIVOS_LIVRES = {"utils/pagination.py", "utils/params.py", "schemas/mixins.py"}

NOMES_DA_SELECAO = {"paginas", "paginas_norm", "paginas_normalizadas"}
# Também os envoltórios de laço (``for p in tqdm(paginas)``), que percorrem a seleção como veio.
CHAMADAS_PROIBIDAS = {"max", "min", "list", "sorted", "set", "tuple", "tqdm", "enumerate", "iter", "reversed"}

# (caminho relativo a src/juscraper, nome qualificado da função) -> motivo.
EXCECOES = {
    ("courts/stf/_collection.py", "Collection.__init__"): (
        "o STF recusa página repetida com ValueError e guarda a lista pedida na identidade do checkpoint"
    ),
    ("courts/tjpr/download.py", "_baixar_paginas"): "``paginas`` já vem resolvida por ``paginas_unicas``",
    ("courts/tjto/download.py", "_baixar_paginas"): "``paginas`` já vem resolvida por ``paginas_no_intervalo``",
    # ``paginas`` com as respostas já baixadas, não a seleção pedida.
    ("courts/_esaj/acordao.py", "EsajAcordaoScraper.baixar_acordao"): "páginas do processo já abertas",
    ("courts/stm/parse.py", "cjsg_parse_manager"): "HTML das páginas baixadas",
    ("courts/tjsp/cposg_download.py", "_incluir_movimentacoes"): "páginas de movimentações do processo",
    ("courts/trf3/parse.py", "_itens"): "respostas JSON baixadas",
    ("utils/divisao_por_data.py", "_sem_repetidos"): "páginas baixadas de cada janela de datas",
}


def _e_selecao(no: ast.AST) -> bool:
    if isinstance(no, ast.Name):
        return no.id in NOMES_DA_SELECAO
    return isinstance(no, ast.Attribute) and no.attr in NOMES_DA_SELECAO


def _menciona_range(no: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "range" for n in ast.walk(no))


def _leitura_a_mao(no: ast.AST) -> tuple[int, str] | None:
    """``(linha, leitura)`` da leitura da seleção feita em ``no``, ou ``None``."""
    if isinstance(no, ast.Attribute) and no.attr in {"start", "stop", "step"} and _e_selecao(no.value):
        return no.lineno, f".{no.attr}"
    if isinstance(no, (ast.Subscript, ast.Starred)) and _e_selecao(no.value):
        return no.lineno, "índice" if isinstance(no, ast.Subscript) else "desempacotamento"
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.args and _e_selecao(no.args[0]):
        if no.func.id in CHAMADAS_PROIBIDAS:
            return no.lineno, f"{no.func.id}()"
        if no.func.id == "isinstance" and len(no.args) > 1 and _menciona_range(no.args[1]):
            return no.lineno, "isinstance(..., range)"
    if isinstance(no, (ast.For, ast.AsyncFor, ast.comprehension)) and _e_selecao(no.iter):
        return no.iter.lineno, "laço"
    return None


def leituras_a_mao(codigo: str) -> list[tuple[int, str, str]]:
    """Lista ``(linha, função, leitura)`` de cada leitura da seleção feita à mão.

    A função é a mais interna que contém a leitura, com o nome qualificado
    pelas classes e funções que a envolvem; fora de função sai ``<módulo>``.
    """
    achados: list[tuple[int, str, str]] = []

    def visitar(no: ast.AST, nomes: tuple[str, ...]) -> None:
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visitar(filho, (*nomes, filho.name))
                continue
            if (achado := _leitura_a_mao(filho)) is not None:
                achados.append((achado[0], ".".join(nomes) or "<módulo>", achado[1]))
            visitar(filho, nomes)

    visitar(ast.parse(codigo), ())
    return achados


def _achados_do_pacote() -> dict[tuple[str, str], list[str]]:
    achados: dict[tuple[str, str], list[str]] = {}
    for arquivo in sorted(RAIZ_PACOTE.rglob("*.py")):
        caminho = arquivo.relative_to(RAIZ_PACOTE).as_posix()
        if caminho in ARQUIVOS_LIVRES:
            continue
        for linha, funcao, leitura in leituras_a_mao(arquivo.read_text(encoding="utf-8")):
            achados.setdefault((caminho, funcao), []).append(f"{linha} ({leitura})")
    return achados


def test_selecao_de_paginas_so_pelos_helpers():
    violacoes = [
        f"src/juscraper/{caminho} em {funcao}: linha {', '.join(linhas)}"
        for (caminho, funcao), linhas in _achados_do_pacote().items()
        if (caminho, funcao) not in EXCECOES
    ]
    assert violacoes == [], (
        "seleção de páginas lida à mão; use os helpers de juscraper.utils.pagination "
        "(paginas_no_intervalo, baixar_paginas_pedidas, menor_pagina, maior_pagina, paginas_unicas):\n"
        + "\n".join(violacoes)
    )


def test_excecoes_ainda_existem():
    assert set(EXCECOES) <= set(_achados_do_pacote())


@pytest.mark.parametrize(
    "codigo",
    [
        "def f(paginas, n):\n    return range(max(1, paginas.start), min(paginas.stop, n + 1), paginas.step)\n",
        "def f(paginas):\n    return paginas[-1] if isinstance(paginas, range) else max(paginas)\n",
        "def f(inp):\n    return min(inp.paginas_normalizadas)\n",
        "def f(paginas, baixar):\n    for p in paginas:\n        baixar(p)\n",
        "def f(paginas, baixar):\n    return [baixar(p) for p in list(paginas)]\n",
        "def f(paginas_norm):\n    return sorted(paginas_norm)\n",
        "def f(paginas):\n    return isinstance(paginas, (list, range))\n",
        "def f(paginas, baixar):\n    for p in tqdm(paginas, desc='x'):\n        baixar(p)\n",
        "def f(paginas):\n    return [i for i, p in enumerate(paginas)]\n",
        "def f(paginas):\n    return [*paginas]\n",
    ],
    ids=[
        "start-stop-step", "isinstance-range-e-max", "min-do-atributo", "laco", "list", "sorted",
        "tupla-de-tipos", "tqdm", "enumerate", "desempacotamento",
    ],
)
def test_leitura_a_mao_e_reprovada(codigo):
    assert leituras_a_mao(codigo)


@pytest.mark.parametrize(
    "codigo",
    [
        "def f(paginas, n):\n    return paginas_no_intervalo(paginas, n, tribunal='TJXX')\n",
        "def f(paginas):\n    return paginas is None or 3 in paginas\n",
        "def f(paginas):\n    return range(menor_pagina(paginas), maior_pagina(paginas) + 1)\n",
        "def f(paginas_iter):\n    return [p for p in paginas_iter]\n",
        "def f(paginas):\n    return isinstance(paginas, list)\n",
    ],
    ids=["helper", "pertinencia", "menor-e-maior", "lista-ja-resolvida", "isinstance-sem-range"],
)
def test_helpers_e_pertinencia_passam(codigo):
    assert leituras_a_mao(codigo) == []


def test_nome_qualificado_aponta_a_funcao_mais_interna():
    codigo = "class C:\n    def m(self, paginas):\n        return list(paginas)\n"
    assert leituras_a_mao(codigo) == [(3, "C.m", "list()")]
