"""Contrato de filtros que usa o builder do raspador precisa ler a requisição enviada.

Um matcher montado com o mesmo builder que o raspador usa
(``json_params_matcher(build_cjsg_payload(...))``, direto ou por um helper
local) confere que o raspador chama o builder, mas não o que o builder produz:
trocar uma chave do backend no builder passa sem reprovar (issue #514; o caso
do TJRO foi o #438, corrigido no #512). Por isso, todo contrato de filtros que
importa um ``build_*`` do pacote tem de ler, no código, a requisição enviada
(``.request.body``, ``.request.params`` ou um leitor de ``tests/_helpers.py``,
como ``corpo_json_enviado``) e compará-la com os nomes de campo do backend
escritos à mão.

A conferência é por arquivo: basta uma leitura da requisição no módulo. O
lugar dela é o teste que passa todos os filtros.
"""
import ast
from functools import cache
from pathlib import Path

import pytest

RAIZ_TESTES = Path(__file__).resolve().parent
ATRIBUTOS_DA_REQUISICAO = {"body", "params"}
# Helpers de tests/_helpers.py que leem o corpo ou a query da requisição enviada.
LEITORES_DA_REQUISICAO = {"corpo_enviado", "corpo_form_enviado", "corpo_json_enviado", "params_enviados"}


def importa_builder(arvore: ast.Module) -> bool:
    """``from juscraper... import build_*`` em qualquer ponto do módulo."""
    return any(
        isinstance(no, ast.ImportFrom)
        and (no.module or "").startswith("juscraper")
        and any(nome.name.startswith("build_") for nome in no.names)
        for no in ast.walk(arvore)
    )


def _le_atributo_da_requisicao(no: ast.AST) -> bool:
    return (
        isinstance(no, ast.Attribute)
        and no.attr in ATRIBUTOS_DA_REQUISICAO
        and isinstance(no.value, ast.Attribute)
        and no.value.attr == "request"
    )


def _chama_leitor_da_requisicao(no: ast.AST) -> bool:
    return isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in LEITORES_DA_REQUISICAO


def le_requisicao_enviada(arvore: ast.Module) -> bool:
    """``<x>.request.body``, ``<x>.request.params`` ou um dos ``LEITORES_DA_REQUISICAO`` no código.

    Docstring e comentário não contam.
    """
    return any(_le_atributo_da_requisicao(no) or _chama_leitor_da_requisicao(no) for no in ast.walk(arvore))


@cache
def _arvore(caminho: Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))


CONTRATOS_DE_FILTROS = sorted(RAIZ_TESTES.glob("*/test_*filters_contract.py"))


@pytest.mark.parametrize(
    "caminho",
    [caminho for caminho in CONTRATOS_DE_FILTROS if importa_builder(_arvore(caminho))],
    ids=lambda caminho: str(caminho.relative_to(RAIZ_TESTES)),
)
def test_contrato_de_filtros_le_a_requisicao_enviada(caminho):
    assert le_requisicao_enviada(_arvore(caminho)), (
        f"{caminho.relative_to(RAIZ_TESTES)} importa o builder do raspador e nenhum "
        "teste lê a requisição enviada. No teste que passa todos os filtros, confira "
        "o corpo (ou a query) contra um dicionário literal com os nomes de campo do "
        "backend, como em tests/tjro/test_cjsg_filters_contract.py."
    )


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("from juscraper.courts.tjpa.download import BASE_URL, build_cjsg_payload", True),
        ("from juscraper.courts.tjpa.download import BASE_URL", False),
        ("from tests._helpers import build_algo", False),
    ],
)
def test_importa_builder(codigo, esperado):
    assert importa_builder(ast.parse(codigo)) is esperado


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("json.loads(responses.calls[0].request.body)", True),
        ("responses.calls[0].request.params == {}", True),
        ("busca.request.url", False),
        ("corpo_form_enviado(busca.request)", True),
        ("corpo_json_enviado(responses.calls[0].request)", True),
        ("params_enviados(responses.calls[0].request)", True),
        ("url_enviada(busca.request)", False),
        ('"""Confere responses.calls[0].request.body."""', False),
        ("# responses.calls[0].request.body", False),
        ("request.body", False),
    ],
)
def test_le_requisicao_enviada(codigo, esperado):
    assert le_requisicao_enviada(ast.parse(codigo)) is esperado
