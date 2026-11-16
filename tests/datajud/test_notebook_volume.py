"""Trava o volume pedido pelos exemplos de ``docs/notebooks/datajud.ipynb`` (#443).

O ``nbmake`` dá 300 s a cada célula. Uma busca por filtro sem ``paginas`` baixa
o índice inteiro do tribunal, em páginas de 5000 processos, e passa desse limite.
"""

import ast
import json
from pathlib import Path

from juscraper.aggregators.datajud.schemas import InputListarProcessosDataJud
from juscraper.utils.params import normalize_paginas

NOTEBOOK = Path(__file__).resolve().parents[2] / "docs" / "notebooks" / "datajud.ipynb"
TAMANHO_PAGINA_DEFAULT = InputListarProcessosDataJud.model_fields["tamanho_pagina"].default
# Teto por célula. Mil processos cabem em poucas buscas pequenas.
TETO_DE_PROCESSOS = 1000


def _valor(no: ast.expr):
    """Avalia o argumento como escrito na célula; só literais e ``range`` são aceitos."""
    return eval(compile(ast.Expression(no), "<notebook>", "eval"), {"__builtins__": {}, "range": range})


def _processos_pedidos(chamada: ast.Call) -> int:
    """Processos que a chamada faz o DataJud percorrer; 0 na busca por CNJ."""
    argumentos = {kw.arg: kw.value for kw in chamada.keywords}
    if "numero_processo" in argumentos:
        # O volume é o da lista de números.
        return 0
    if chamada.args:  # ``paginas`` é o único parâmetro posicional
        argumentos["paginas"] = chamada.args[0]
    trecho = ast.unparse(chamada)
    paginas = normalize_paginas(_valor(argumentos["paginas"])) if "paginas" in argumentos else None
    assert paginas is not None, f"sem `paginas`, a busca baixa o índice inteiro: {trecho}"
    tamanho: int = _valor(argumentos["tamanho_pagina"]) if "tamanho_pagina" in argumentos else TAMANHO_PAGINA_DEFAULT
    # O cursor ``search_after`` percorre as páginas anteriores à primeira pedida.
    return max(paginas) * tamanho


def _chamadas_por_celula() -> list[list[ast.Call]]:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    celulas = []
    for celula in notebook["cells"]:
        if celula["cell_type"] != "code":
            continue
        arvore = ast.parse("".join(celula["source"]))
        celulas.append(
            [
                no
                for no in ast.walk(arvore)
                if isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr == "listar_processos"
            ]
        )
    return celulas


def test_exemplos_pedem_volume_limitado():
    celulas = _chamadas_por_celula()
    assert any(celulas), "o notebook deixou de chamar listar_processos"

    for chamadas in celulas:
        pedido = sum(_processos_pedidos(chamada) for chamada in chamadas)
        trechos = "; ".join(ast.unparse(chamada) for chamada in chamadas)
        assert pedido <= TETO_DE_PROCESSOS, f"{pedido} processos pedidos numa célula: {trechos}"
