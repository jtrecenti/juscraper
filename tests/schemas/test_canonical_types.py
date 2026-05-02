"""Rede de seguranca contra drift de nomes canonicos e tipos de campo.

Dois enforcamentos em schemas concretos Input/Output (mapeados em
:mod:`tests.schemas.test_schema_coverage` e :mod:`tests.schemas.test_output_parity`):

1. **Tipos consistentes para nomes canonicos** — um campo cujo nome
   coincide com um campo das bases/mixins deve ter o mesmo tipo
   declarado. Input e Output tem palettes separadas (p.ex. ``id_cnj``
   e ``str | list[str]`` no Input, ``str`` no Output).

2. **Nomes deprecados sao proibidos** em schemas novos — a tabela de
   "Nomes canonicos de coluna" do ``CLAUDE.md`` listou quais sinonimos
   foram unificados. Declarar um nome deprecado num schema novo volta
   a divergencia e quebra o teste.

:data:`TYPE_GRACE_PERIOD` e :data:`SYNONYM_GRACE_PERIOD` documentam
excecoes conhecidas que ainda aparecem por razao explicita — p.ex.
TJPI/TJGO nao convertem ``data_publicacao`` para ``date``, DataJud
ainda so aceita ``range`` na assinatura, ``OutputCJSGEsaj`` declara
``relatora`` por causa do parser ``_normalize_key``. Cada entrada
tem a razao e o PR pendente.
"""
from __future__ import annotations

import importlib

import pytest
from pydantic import BaseModel

from juscraper.schemas import (
    CnjInputBase,
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputCJSGBase,
    OutputCnjConsultaBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)
from tests.schemas.test_output_parity import EXPECTED_AGGREGATOR_OUTPUT_SCHEMAS, EXPECTED_COURT_OUTPUT_SCHEMAS
from tests.schemas.test_schema_coverage import EXPECTED_AGGREGATOR_SCHEMAS, EXPECTED_COURT_SCHEMAS

# Fonte da verdade Input: bases/mixins que concretos de Input podem
# herdar/redeclarar. Cada campo declarado aqui fixa o tipo canonico.
_INPUT_BASES = (
    SearchBase,
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    CnjInputBase,
)

# Fonte da verdade Output: bases/mixins de Output.
_OUTPUT_BASES = (
    OutputCJSGBase,
    OutputRelatoriaMixin,
    OutputDataPublicacaoMixin,
    OutputCnjConsultaBase,
)


def _collect(bases):
    out: dict[str, object] = {}
    for base in bases:
        for field_name, info in base.model_fields.items():
            out[field_name] = info.annotation
    return out


CANONICAL_INPUT_TYPES = _collect(_INPUT_BASES)
CANONICAL_OUTPUT_TYPES = _collect(_OUTPUT_BASES)


# Sinonimos deprecados: aparecer num schema concreto Input/Output e bug.
# Mensagem explica o canonico para facilitar a correcao.
DEPRECATED_SYNONYMS: dict[str, str] = {
    "magistrado": "relator",
    "nr_processo": "numero_processo (Input) / processo (Output)",
    "numero_unico": "processo (Output)",
    "numero_cnj": "numero_processo (Input) / id_cnj em consulta CNJ",
    "classe_cnj": "classe",
    "classe_judicial": "classe",
    "assunto_cnj": "assunto",
    "assunto_principal": "assunto",
}


# Excecoes de tipo keyed por (nome_da_classe, nome_do_campo). Documentam
# divergencias conhecidas com o PR pendente. Remover a entrada quando
# o PR de correcao entrar.
TYPE_GRACE_PERIOD: dict[tuple[str, str], str] = {
    # DataJud listar_processos aceita apenas ``range`` hoje; o contrato
    # canonico de SearchBase e ``int | list[int] | range | None``.
    # Ver xfail em test_paginas_acceptance.py. Corrigir em PR proprio
    # ajustando a assinatura do client + o schema.
    (
        "InputListarProcessosDataJud",
        "paginas",
    ): "DataJud listar_processos so aceita range — PR proprio pendente (ver xfail em test_paginas_acceptance)",
    # TJPI e TJGO entregam data_publicacao sempre como string crua (nao
    # convertem para datetime.date). O canonico do mixin e
    # ``date | str | None`` (mais permissivo). Migrar o parser para
    # converter para date unifica o tipo.
    (
        "OutputCJSGTJPI",
        "data_publicacao",
    ): "TJPI parser nao converte data_publicacao para date — unificar em PR de limpeza",
    (
        "OutputCJSGTJGO",
        "data_publicacao",
    ): "TJGO parser nao converte data_publicacao para date — unificar em PR de limpeza",
}


# Excecoes de sinonimo keyed por (nome_da_classe, nome_do_campo).
# Documentam tribunais que ainda nao passaram pelo rename canonico
# mas estao na agenda.
SYNONYM_GRACE_PERIOD: dict[tuple[str, str], str] = {
    # OutputCJSGEsaj declara ``relatora`` explicito porque o parser eSAJ
    # _normalize_key transforma "Relator(a):" em "relatora". Correcao
    # estrutural no parser e breaking para 6 tribunais — PR dedicado.
    (
        "OutputCJSGEsaj",
        "relatora",
    ): "eSAJ parser emite relatora via _normalize_key — PR dedicado pendente (ver TODO no docstring)",
}


def _resolve(module_path: str, class_name: str) -> type[BaseModel]:
    mod = importlib.import_module(module_path)
    cls: type[BaseModel] = getattr(mod, class_name)
    return cls


def _is_output(class_name: str) -> bool:
    return class_name.startswith("Output")


def _all_schema_cases():
    """Toda classe Input + Output mapeada, deduplicada por (module, class)."""
    seen: set[tuple[str, str]] = set()
    cases: list[pytest.ParameterSet] = []
    for mapping in (
        EXPECTED_COURT_SCHEMAS,
        EXPECTED_AGGREGATOR_SCHEMAS,
        EXPECTED_COURT_OUTPUT_SCHEMAS,
        EXPECTED_AGGREGATOR_OUTPUT_SCHEMAS,
    ):
        for (tribunal, endpoint), (module_path, class_name) in mapping.items():
            key = (module_path, class_name)
            if key in seen:
                continue
            seen.add(key)
            cases.append(
                pytest.param(
                    module_path,
                    class_name,
                    id=f"{tribunal}.{endpoint}.{class_name}",
                )
            )
    return cases


SCHEMA_CASES = _all_schema_cases()


@pytest.mark.parametrize("module_path,class_name", SCHEMA_CASES)
def test_canonical_field_types_are_consistent(module_path, class_name):
    """Campos com nome canonico carregam o tipo declarado na base/mixin.

    Input e Output tem palettes separadas: um campo ``id_cnj`` num Input
    segue ``CnjInputBase`` (``str | list[str]``); num Output segue
    ``OutputCnjConsultaBase`` (``str``).
    """
    schema_cls = _resolve(module_path, class_name)
    palette = CANONICAL_OUTPUT_TYPES if _is_output(class_name) else CANONICAL_INPUT_TYPES
    divergencias: list[str] = []
    for name, info in schema_cls.model_fields.items():
        if name not in palette:
            continue
        if (class_name, name) in TYPE_GRACE_PERIOD:
            continue
        canonical = palette[name]
        if info.annotation != canonical:
            divergencias.append(
                f"{name}: declarado como {info.annotation!r}, canonico e {canonical!r}"
            )
    if divergencias:
        items = "\n * ".join(divergencias)
        pytest.fail(
            f"{class_name} diverge do tipo canonico (fonte: bases/mixins em "
            f"juscraper.schemas):\n * {items}"
        )


@pytest.mark.parametrize("module_path,class_name", SCHEMA_CASES)
def test_no_deprecated_synonyms_in_schemas(module_path, class_name):
    """Nenhum schema concreto declara um sinonimo deprecado.

    Scraper novo que tentar declarar ``classes`` (plural) onde o conceito
    e igual a ``classe`` (singular) vai bater aqui; idem para
    ``magistrado``, ``nr_processo``, ``classe_cnj`` etc. Ver a tabela
    "Nomes canonicos de coluna" do CLAUDE.md.
    """
    schema_cls = _resolve(module_path, class_name)
    proibidos: list[str] = []
    for name in schema_cls.model_fields:
        if name not in DEPRECATED_SYNONYMS:
            continue
        if (class_name, name) in SYNONYM_GRACE_PERIOD:
            continue
        proibidos.append(f"{name} (use {DEPRECATED_SYNONYMS[name]})")
    if proibidos:
        items = "\n * ".join(proibidos)
        pytest.fail(
            f"{class_name} declara sinonimo deprecado:\n * {items}\n"
            "CLAUDE.md > 'Nomes canonicos de coluna' documenta o motivo."
        )


def test_grace_period_exceptions_are_still_needed():
    """Cada grace-period exception aparece no schema que referencia.

    Impede que a lista cresca silenciosamente: quando o PR de correcao
    entra, essa entrada precisa sair daqui junto — se nao sair, o teste
    falha lembrando de limpar.
    """
    orphans: list[str] = []

    def _check(class_name: str, field_name: str, kind: str):
        # Acha o modulo via EXPECTED_*; caso o schema tenha sido removido
        # do mapeamento, e obviamente orphan.
        for mapping in (
            EXPECTED_COURT_SCHEMAS,
            EXPECTED_AGGREGATOR_SCHEMAS,
            EXPECTED_COURT_OUTPUT_SCHEMAS,
            EXPECTED_AGGREGATOR_OUTPUT_SCHEMAS,
        ):
            for _, (module_path, cn) in mapping.items():
                if cn != class_name:
                    continue
                schema_cls = _resolve(module_path, class_name)
                if field_name in schema_cls.model_fields:
                    return
        orphans.append(f"{kind}: {class_name}.{field_name}")

    for (class_name, field_name) in TYPE_GRACE_PERIOD:
        _check(class_name, field_name, "TYPE_GRACE_PERIOD")
    for (class_name, field_name) in SYNONYM_GRACE_PERIOD:
        _check(class_name, field_name, "SYNONYM_GRACE_PERIOD")

    assert not orphans, (
        "Grace-period exceptions que ja nao aparecem no schema (remover "
        "da lista — a correcao provavelmente ja entrou):\n  - "
        + "\n * ".join(orphans)
    )
