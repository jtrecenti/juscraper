"""Parametro explicito do metodo publico tem a anotacao do campo do schema.

Para cada par (schema ``Input*`` mapeado em
:mod:`tests.schemas.test_schema_coverage`, metodo publico ``<endpoint>`` ou
``<endpoint>_download``), todo campo do schema que e parametro explicito do
metodo precisa ter na assinatura a anotacao do schema
(``model_fields[campo].annotation``). Sem isso, o editor e o mypy do usuario
aceitam o que o pydantic recusa (``tipo_decisao="acordao"``) ou recusam o que
funciona.

A assinatura so difere do schema quando o pipeline aceita mais do que o schema
declara, porque converte o valor antes do pydantic. Essas diferencas sao regras
por categoria (:data:`REGRAS`); campo a campo, so :data:`AMPLIADOS` e
:data:`ESPECIFICAS`, cada uma com o motivo. Regra ou excecao sem uso reprova.
"""
from __future__ import annotations

import inspect
import typing
from collections.abc import Callable, Iterable
from datetime import date

import pytest
from pydantic.fields import FieldInfo

from juscraper.schemas import PaginasMixin
from juscraper.utils.params import DATE_CANONICAL
from tests.schemas.test_schema_coverage import (
    EXPECTED_AGGREGATOR_SCHEMAS,
    EXPECTED_COURT_SCHEMAS,
    _is_stub,
    _iter_aggregator_scrapers,
    _iter_court_scrapers,
    _resolve,
    _schemas_mapeados,
)


class Caso(typing.NamedTuple):
    sigla: str
    metodo_nome: str
    campo: str
    metodo: Callable[..., object]
    info: FieldInfo
    parametro: inspect.Parameter


#: Anotacao canonica de ``paginas`` nas assinaturas. ``normalize_paginas`` roda
#: antes do pydantic e aceita qualquer ``list``; o pydantic coage os itens
#: (``np.int64(2)``, ``"3"``). ``list[int]`` recusaria ``list[np.int64]`` no mypy.
PAGINAS_ASSINATURA = int | list | range | None

def _regra_data_canonica(caso: Caso) -> object:
    """Data canonica aceita ``date``, que o pipeline converte antes do pydantic.

    Ver :class:`juscraper.schemas.DataJulgamentoMixin` e ``test_date_annotations``.
    """
    if caso.campo in DATE_CANONICAL:
        return caso.info.annotation | date
    return None


def _regra_paginas(caso: Caso) -> object:
    """``paginas`` herdado de :class:`PaginasMixin` usa :data:`PAGINAS_ASSINATURA`."""
    if caso.campo == "paginas" and caso.info.annotation == PaginasMixin.model_fields["paginas"].annotation:
        return PAGINAS_ASSINATURA
    return None


def _regra_none_usa_o_padrao(caso: Caso) -> object:
    """``None`` como "usa o padrao do schema": o metodo nao repassa o ``None`` ao pydantic."""
    info = caso.info
    if caso.parametro.default is None and not info.is_required() and not _aceita_none(info.annotation):
        return info.annotation | None
    return None


def _regra_none_via_alias(caso: Caso) -> object:
    """``pesquisa`` obrigatorio tem default ``None`` para o termo vir por alias deprecado.

    Os aliases sao os de :data:`juscraper.utils.params.SEARCH_ALIASES`, resolvidos
    antes do pydantic; sem termo nenhum, o pipeline levanta ``TypeError``.
    """
    if caso.campo == "pesquisa" and caso.info.is_required() and caso.parametro.default is None:
        return caso.info.annotation | None
    return None


#: Diferencas legitimas entre assinatura e schema, por categoria. A primeira
#: que se aplica ao campo da a anotacao esperada; sem nenhuma, vale a do schema.
REGRAS: dict[str, Callable[[Caso], object]] = {
    "data_canonica": _regra_data_canonica,
    "paginas": _regra_paginas,
    "none_usa_o_padrao": _regra_none_usa_o_padrao,
    "none_via_alias": _regra_none_via_alias,
}

#: Assinatura mais larga que um ``Literal`` do schema: aceita, alem dos valores
#: dele, o que o pipeline converte antes do pydantic. Precisa continuar restrita
#: a ``Literal`` (mais ``None``/``bool``), nunca ``str`` ou ``int`` livres.
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

#: Anotacao propria de um campo, fora das regras: ``(sigla, campo) -> (anotacao, motivo)``.
ESPECIFICAS: dict[tuple[str, str], tuple[object, str]] = {
    ("pdpj", "paginas"): (
        int | list[int] | range | None,
        "PdpjScraper.pesquisa anota list[int], mais estreito que PAGINAS_ASSINATURA; "
        "apareceu quando o endpoint entrou no mapa de schemas. Alinhar a assinatura "
        "fica para um PR proprio, porque muda a API publica",
    ),
    ("tjrs", "secao"): (
        str | None,
        'texto livre: o schema ignora caixa, acento e espacos ("Cível" vira "civel") '
        "antes de comparar com o Literal",
    ),
    ("tjsp", "id_cnj"): (
        str | Iterable[str],
        "_lista_de_cnjs converte qualquer iteravel em list antes do schema",
    ),
}


def _aceita_none(anotacao: object) -> bool:
    return anotacao is None or type(None) in typing.get_args(anotacao)


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


def _esperada(caso: Caso) -> tuple[str, object]:
    """Origem (regra, excecao ou ``"schema"``) e anotacao esperada na assinatura.

    Em :data:`AMPLIADOS`, nao ha anotacao exata: :func:`_confere_ampliado` confere a forma.
    """
    if (caso.sigla, caso.campo) in AMPLIADOS:
        return "AMPLIADOS", None
    if (caso.sigla, caso.campo) in ESPECIFICAS:
        return "ESPECIFICAS", ESPECIFICAS[caso.sigla, caso.campo][0]
    for nome, regra in REGRAS.items():
        esperada = regra(caso)
        if esperada is not None:
            return nome, esperada
    return "schema", caso.info.annotation


def _casos() -> list[Caso]:
    casos: list[Caso] = []
    for par in _schemas_mapeados(EXPECTED_COURT_SCHEMAS, _iter_court_scrapers) + _schemas_mapeados(
        EXPECTED_AGGREGATOR_SCHEMAS, _iter_aggregator_scrapers
    ):
        schema = _resolve(par.modulo, par.classe)
        assert schema is not None, f"{par.modulo}:{par.classe} nao encontrado"
        for nome in (par.endpoint, f"{par.endpoint}_download"):
            metodo = getattr(par.raspador, nome, None)
            if metodo is None or _is_stub(metodo):
                continue
            parametros = inspect.signature(metodo).parameters
            casos.extend(
                Caso(par.sigla, nome, campo, metodo, info, parametros[campo])
                for campo, info in schema.model_fields.items()
                if campo in parametros
            )
    return casos


CASOS = _casos()


def test_ha_parametros_explicitos_com_campo_no_schema():
    assert len(CASOS) > 400
    assert sum(1 for caso in CASOS if _valores_literal(caso.info.annotation)) > 40


def test_excecoes_existem():
    """Excecao sem caso correspondente esta obsoleta: remova-a."""
    existentes = {(caso.sigla, caso.campo) for caso in CASOS}
    assert not (AMPLIADOS.keys() | ESPECIFICAS.keys()) - existentes


def test_regras_em_uso():
    """Regra que nenhum caso usa esta obsoleta: remova-a."""
    usadas = {_esperada(caso)[0] for caso in CASOS}
    assert not REGRAS.keys() - usadas


@pytest.mark.parametrize("caso", CASOS, ids=[f"{c.sigla}.{c.metodo_nome}.{c.campo}" for c in CASOS])
def test_assinatura_anota_o_tipo_do_schema(caso: Caso):
    anotacao = typing.get_type_hints(caso.metodo)[caso.campo]
    anotacao_schema = caso.info.annotation
    local = f"{caso.sigla}.{caso.metodo_nome}({caso.campo})"
    origem, esperada = _esperada(caso)
    if origem == "AMPLIADOS":
        _confere_ampliado(local, anotacao, anotacao_schema)
        return
    assert anotacao == esperada, (
        f"{local} esta anotado como {anotacao}, mas o esperado ({origem}) e {esperada}; "
        f"o schema declara {anotacao_schema}. Use na assinatura o tipo do schema, ou "
        "registre a diferenca numa regra ou excecao deste arquivo, com o motivo."
    )


def _confere_ampliado(local: str, anotacao: object, anotacao_schema: object) -> None:
    assert anotacao != anotacao_schema, f"{local} ja bate com o schema: remova-o de AMPLIADOS."
    valores_schema = _valores_literal(anotacao_schema)
    valores = _valores_literal(anotacao)
    assert valores_schema, f"{local} nao e Literal no schema: tire-o de AMPLIADOS."
    faltam = valores_schema - valores
    assert not faltam, f"{local} nao aceita {faltam}, que o schema aceita."
    livres = _tipos_livres(anotacao) - {type(None), bool}
    assert not livres, f"{local} aceita {livres} livre; restrinja a valores Literal."
    # Assinatura com codigos em ``int`` (que o schema converte em ``str``) repete todos eles.
    if any(type(valor) is int for valor in valores):
        sem_int = {v for v in valores_schema if isinstance(v, str) and v.isdigit() and int(v) not in valores}
        assert not sem_int, f"{local} nao aceita em int os codigos {sem_int}, que o schema aceita em str."
