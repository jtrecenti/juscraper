"""Gates da conferência de páginas em ``src/juscraper/courts/`` e ``aggregators/``.

Regra (CONTRIBUTING > Contagem de páginas e resultados em HTML): toda
resposta é conferida como a página esperada antes de se ler algo dela;
contagem ausente levanta; página pedida dentro do total traz ao menos um item
e não repete outra. Os dois gates reprovam as formas mais comuns de quebrar a
regra:

* **Contagem com default.** ``x or 0``, ``x or 1``, ``.get("total", 0)``,
  ``n if n is not None else 0`` e ``if n is None: return 1`` transformam a
  página de erro, que não traz a contagem, em busca vazia ou página única, e
  o download para na primeira página sem aviso. A contagem ausente vai como
  ``None`` para :func:`~juscraper.utils.pagination.resolve_total_pages`, que
  levanta (no JSON, por :func:`~juscraper.utils.pagination.contagem_json`).
* **``baixar_paginas_pedidas`` sem ``n_itens=``.** Sem ele, a página 2..N que
  volta de outro tipo, vazia dentro do total ou repetindo a anterior entra no
  resultado sem erro.

Os achados de hoje ficam em ``EXCECOES``, com quantos são e o motivo; cada
sessão de adoção retira os seus. Exceção com número de achados diferente
reprova: achado novo num arquivo da lista também é pego, e o que foi corrigido
sai dela.

Fragilidades conhecidas: o gate de default reconhece só a constante 0 ou 1
literal (``or default``, ``max(n, 1)``, ``try/except: return 0`` e
``getattr(r, "total", 0)`` passam) e, no ``.get``, só as chaves de
``_CHAVES_DE_CONTAGEM``; ``or 0`` fora de contagem (soma de conferência)
entra em ``EXCECOES``. O gate de ``n_itens`` vê só a chamada pelo nome
``baixar_paginas_pedidas``; laço próprio usa ``ConferenciaDePaginas`` e fica fora.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

RAIZ_PACOTE = Path(__file__).resolve().parents[1] / "src" / "juscraper"
PASTAS = ("courts", "aggregators")

_CHAVES_DE_CONTAGEM = re.compile(
    r"total|count|numFound|TotalDocs|pageCount|itemCount|totalPages|total_pages|last|value", re.IGNORECASE
)

_SESSAO_JSF = "pendente: sessão de adoção 1 (JSF/sessão: TJPE, TJRR, TJMG, TJRJ)"
_SESSAO_PAGINAS = "pendente: sessão de adoção 2 (baixar_paginas_pedidas com n_itens)"
_SESSAO_JSON = "pendente: sessão de adoção 3 (contagem estrita nos JSON)"
_SESSAO_PJE = "pendente: sessão de adoção 6 (_trf/PJe, TRF3 cpopg e TJSP show.do)"

# Caminho relativo a src/juscraper -> (achados, motivo).
EXCECOES_DEFAULT = {
    "courts/stf/_checkpoint.py": (1, "soma de conferência das janelas filhas, não default de contagem"),
    "courts/stf/_collection.py": (1, "soma de conferência das janelas filhas, não default de contagem"),
    "courts/tjba/download.py": (2, _SESSAO_JSON),
    "courts/tjes/download.py": (1, _SESSAO_JSON),
    "courts/tjmg/download.py": (1, _SESSAO_JSF),
    "courts/tjpa/download.py": (1, _SESSAO_JSON),
    "courts/tjpb/download.py": (1, _SESSAO_JSON),
    "courts/tjpe/download.py": (1, "pendente: #807 (TJPE: contagem ausente levanta)"),
    "courts/tjrj/download.py": (1, _SESSAO_JSON),
    "courts/tjrn/download.py": (1, _SESSAO_JSON),
    "courts/tjro/download.py": (3, _SESSAO_JSON),
    "courts/tjrs/download.py": (1, _SESSAO_JSON),
    "courts/trf3/download.py": (1, _SESSAO_PJE),
}

EXCECOES_N_ITENS = dict.fromkeys(
    (
        "courts/tjba/download.py",
        "courts/tjdft/download.py",
        "courts/tjes/download.py",
        "courts/tjmg/download.py",
        "courts/tjmt/download.py",
        "courts/tjpa/download.py",
        "courts/tjpb/download.py",
        "courts/tjpi/download.py",
        "courts/tjpr/download.py",
        "courts/tjrn/download.py",
        "courts/tjro/download.py",
        "courts/tjrs/download.py",
        "courts/tjsc/download.py",
        "courts/tjto/download.py",
    ),
    (1, _SESSAO_PAGINAS),
)


def _zero_ou_um(no: ast.AST | None) -> bool:
    return isinstance(no, ast.Constant) and type(no.value) is int and no.value in (0, 1)


def _compara_com_none(no: ast.AST, operador: type[ast.cmpop]) -> bool:
    return (
        isinstance(no, ast.Compare)
        and any(isinstance(op, operador) for op in no.ops)
        and any(isinstance(c, ast.Constant) and c.value is None for c in no.comparators)
    )


def _default_de_contagem(no: ast.expr | ast.stmt) -> str | None:
    """Descreve o default de contagem em ``no``, ou ``None``."""
    if isinstance(no, ast.BoolOp) and isinstance(no.op, ast.Or) and _zero_ou_um(no.values[-1]):
        return "or 0/1"
    if (
        isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr == "get"
        and len(no.args) == 2
        and isinstance(no.args[0], ast.Constant)
        and isinstance(no.args[0].value, str)
        and _CHAVES_DE_CONTAGEM.fullmatch(no.args[0].value)
        and _zero_ou_um(no.args[1])
    ):
        return f".get({no.args[0].value!r}, 0/1)"
    if isinstance(no, ast.IfExp) and _zero_ou_um(no.orelse) and _compara_com_none(no.test, ast.IsNot):
        return "x if x is not None else 0/1"
    if (
        isinstance(no, ast.If)
        and _compara_com_none(no.test, ast.Is)
        and len(no.body) == 1
        and isinstance(no.body[0], ast.Return)
        and _zero_ou_um(no.body[0].value)
    ):
        return "if x is None: return 0/1"
    return None


def defaults_de_contagem(codigo: str) -> list[tuple[int, str]]:
    """Lista ``(linha, forma)`` de cada default de contagem no código."""
    nos = (no for no in ast.walk(ast.parse(codigo)) if isinstance(no, ast.expr | ast.stmt))
    return sorted((no.lineno, forma) for no in nos if (forma := _default_de_contagem(no)))


def baixar_sem_n_itens(codigo: str) -> list[int]:
    """Linhas das chamadas a ``baixar_paginas_pedidas`` sem ``n_itens=``."""
    linhas = []
    for no in ast.walk(ast.parse(codigo)):
        if not isinstance(no, ast.Call):
            continue
        nome = getattr(no.func, "id", None) or getattr(no.func, "attr", None)
        if nome == "baixar_paginas_pedidas" and not any(k.arg == "n_itens" for k in no.keywords):
            linhas.append(no.lineno)
    return sorted(linhas)


def _achados(regra) -> dict[str, list]:
    achados = {}
    for pasta in PASTAS:
        for arquivo in sorted((RAIZ_PACOTE / pasta).rglob("*.py")):
            if encontrados := regra(arquivo.read_text(encoding="utf-8")):
                achados[arquivo.relative_to(RAIZ_PACOTE).as_posix()] = encontrados
    return achados


def _divergencias(achados: dict[str, list], excecoes: dict[str, tuple[int, str]]) -> dict[str, str]:
    divergencias = {}
    for caminho in sorted(set(achados) | set(excecoes)):
        n_achados = len(achados.get(caminho, []))
        n_esperado = excecoes.get(caminho, (0, ""))[0]
        if n_achados != n_esperado:
            divergencias[caminho] = f"{n_achados} achado(s), EXCECOES espera {n_esperado}: {achados.get(caminho)}"
    return divergencias


def test_contagem_sem_default():
    divergencias = _divergencias(_achados(defaults_de_contagem), EXCECOES_DEFAULT)
    assert not divergencias, (
        "Contagem com default (or 0/1, .get(chave, 0/1), 'if x is None' com 0/1): passe a contagem "
        "ausente como None para resolve_total_pages, que levanta (no JSON, por contagem_json). "
        "Arquivo corrigido sai de EXCECOES_DEFAULT; o número de achados de cada exceção tem que bater. "
        f"Divergências: {divergencias}"
    )


def test_baixar_paginas_pedidas_com_n_itens():
    divergencias = _divergencias(_achados(baixar_sem_n_itens), EXCECOES_N_ITENS)
    assert not divergencias, (
        "baixar_paginas_pedidas sem n_itens=: passe n_itens (itens da página; None para página que não "
        "é de resultados) e, com identificador por item, chaves=. Arquivo corrigido sai de "
        f"EXCECOES_N_ITENS. Divergências: {divergencias}"
    )


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("n = total or 0\n", [(1, "or 0/1")]),
        ("n = math.ceil(t / 20) or 1\n", [(1, "or 0/1")]),
        ("n = d.get('total', 0)\n", [(1, ".get('total', 0/1)")]),
        ("n = d['hits'].get('numFound', 0)\n", [(1, ".get('numFound', 0/1)")]),
        ("n = d.get('pageCount', 1)\n", [(1, ".get('pageCount', 0/1)")]),
        ("n = x if x is not None else 0\n", [(1, "x if x is not None else 0/1")]),
        ("def f(x):\n    if x is None:\n        return 1\n    return x\n", [(2, "if x is None: return 0/1")]),
        ("n = d.get('total')\n", []),
        ("n = d.get('nome', 0)\n", []),
        ("n = x or 2\n", []),
        ("n = x or default\n", []),
        ("n = x if x is not None else default\n", []),
        ("def f(x):\n    if x is None:\n        raise ValueError\n", []),
    ],
)
def test_defaults_de_contagem(codigo, esperado):
    assert defaults_de_contagem(codigo) == esperado


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("baixar_paginas_pedidas(p, b, c, tribunal='X')\n", [1]),
        ("pagination.baixar_paginas_pedidas(p, b, c, tribunal='X')\n", [1]),
        ("baixar_paginas_pedidas(p, b, c, tribunal='X', n_itens=contar)\n", []),
        ("def baixar_paginas_pedidas(p, b, c):\n    pass\n", []),
    ],
)
def test_baixar_sem_n_itens(codigo, esperado):
    assert baixar_sem_n_itens(codigo) == esperado
