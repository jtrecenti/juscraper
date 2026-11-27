"""Filtro com valores fixos no schema tem a mesma anotacao na assinatura publica.

Para cada par (schema ``Input*`` mapeado em
:mod:`tests.schemas.test_schema_coverage`, metodo publico ``<endpoint>`` ou
``<endpoint>_download``), todo campo do schema anotado com ``Literal`` que e
parametro explicito do metodo precisa ter na assinatura a mesma anotacao do
schema. Sem isso, o editor e o mypy aceitam ``tipo_decisao="acordao"``, que so
falha com ``ValidationError`` em tempo de execucao.

Quando o pipeline aceita mais do que o schema declara (valor deprecado trocado
antes do pydantic, ``int`` convertido em ``str`` por validador), a assinatura
tambem aceita, e o campo entra em :data:`AMPLIADOS` com o motivo.
"""
from __future__ import annotations

import inspect
import typing
from collections.abc import Callable

import pytest

from tests.schemas.test_schema_coverage import (
    EXPECTED_AGGREGATOR_SCHEMAS,
    EXPECTED_COURT_SCHEMAS,
    _is_stub,
    _iter_aggregator_scrapers,
    _iter_court_scrapers,
    _resolve,
)

#: Assinatura mais larga que o schema: aceita, alem dos valores dele, o que o
#: pipeline converte antes do pydantic. Precisa continuar restrita a ``Literal``
#: (mais ``None``/``bool``), nunca ``str`` ou ``int`` livres.
AMPLIADOS: dict[tuple[str, str], str] = {
    ("tjap", "votacao"): '"Unanime", deprecado, vira "Unânime" antes do schema',
    ("tjdft", "buscar_em"): "bool do alias deprecado inteiro_teor (por posicao) e None (default do schema)",
    ("tjgo", "id_instancia"): "2 e 3, deprecados, viram 151 e 15 antes do schema",
    ("tjgo", "id_serventia_subtipo"): "int, que o BeforeValidator do schema converte em str",
    ("tjpa", "buscar_em"): 'valores do alias deprecado query_scope ("inteiroTeor") e None (default do schema)',
    ("tjrj", "competencia"): "int, que o field_validator do schema converte em str",
    ("tjrj", "origem"): "int, que o field_validator do schema converte em str",
    ("tjsc", "buscar_em"): 'valores do alias deprecado campo ("E"/"I", por posicao) e None (default do schema)',
}

#: Texto livre que o schema normaliza antes de comparar com o ``Literal``: a
#: assinatura fica com ``str``, porque um ``Literal`` recusaria valores aceitos.
TEXTO_LIVRE: dict[tuple[str, str], str] = {
    ("tjrs", "secao"): 'o schema ignora caixa, acento e espacos ("Cível" vira "civel")',
}


def _tem_literal(anotacao: object) -> bool:
    return typing.get_origin(anotacao) is typing.Literal or any(
        _tem_literal(arg) for arg in typing.get_args(anotacao)
    )


def _valores_literal(anotacao: object) -> set[object]:
    if typing.get_origin(anotacao) is typing.Literal:
        return set(typing.get_args(anotacao))
    return {valor for arg in typing.get_args(anotacao) for valor in _valores_literal(arg)}


def _tipos_livres(anotacao: object) -> set[object]:
    """Tipos da anotacao fora de ``Literal`` (``str`` em ``str | None``)."""
    if typing.get_origin(anotacao) is typing.Literal:
        return set()
    args = typing.get_args(anotacao)
    if not args:
        return {anotacao}
    return {tipo for arg in args for tipo in _tipos_livres(arg)}


Caso = tuple[str, str, str, Callable[..., object], object]


def _casos() -> list[Caso]:
    casos: list[Caso] = []
    for mapa, iterar in (
        (EXPECTED_COURT_SCHEMAS, _iter_court_scrapers),
        (EXPECTED_AGGREGATOR_SCHEMAS, _iter_aggregator_scrapers),
    ):
        raspadores = dict(iterar())
        for (sigla, endpoint), (modulo, classe) in sorted(mapa.items()):
            schema = _resolve(modulo, classe)
            assert schema is not None, f"{modulo}:{classe} nao encontrado"
            for nome in (endpoint, f"{endpoint}_download"):
                metodo = getattr(raspadores[sigla], nome, None)
                if metodo is None or _is_stub(metodo):
                    continue
                parametros = inspect.signature(metodo).parameters
                casos.extend(
                    (sigla, nome, campo, metodo, info.annotation)
                    for campo, info in schema.model_fields.items()
                    if campo in parametros and _tem_literal(info.annotation)
                )
    return casos


TODOS = _casos()
CASOS = [caso for caso in TODOS if (caso[0], caso[2]) not in TEXTO_LIVRE]


def test_ha_campos_literal_nas_assinaturas():
    assert len(CASOS) > 40


def test_excecoes_existem():
    """Excecao sem caso correspondente esta obsoleta: remova-a."""
    existentes = {(sigla, campo) for sigla, _, campo, _, _ in TODOS}
    assert not (AMPLIADOS.keys() | TEXTO_LIVRE.keys()) - existentes


@pytest.mark.parametrize(
    ("sigla", "metodo_nome", "campo", "metodo", "anotacao_schema"),
    CASOS,
    ids=[f"{s}.{m}.{c}" for s, m, c, _, _ in CASOS],
)
def test_assinatura_anota_o_dominio_do_schema(sigla, metodo_nome, campo, metodo, anotacao_schema):
    anotacao = typing.get_type_hints(metodo)[campo]
    local = f"{sigla}.{metodo_nome}({campo})"
    if (sigla, campo) not in AMPLIADOS:
        assert anotacao == anotacao_schema, (
            f"{local} esta anotado como {anotacao}, mas o schema aceita {anotacao_schema}: "
            "use na assinatura o alias Literal do schema."
        )
        return
    assert anotacao != anotacao_schema, f"{local} ja bate com o schema: remova-o de AMPLIADOS."
    faltam = _valores_literal(anotacao_schema) - _valores_literal(anotacao)
    assert not faltam, f"{local} nao aceita {faltam}, que o schema aceita."
    livres = _tipos_livres(anotacao) & {str, int}
    assert not livres, f"{local} aceita {livres} livre; restrinja a valores Literal."
