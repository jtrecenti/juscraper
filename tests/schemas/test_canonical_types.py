"""Rede de seguranca contra drift de nomes canonicos e tipos de campo.

Dois enforcamentos em schemas concretos Input/Output (mapeados em
:mod:`tests.schemas._registro`):

1. **Tipos consistentes para nomes canonicos** — um campo cujo nome
   coincide com um campo das bases/mixins deve ter o mesmo tipo
   declarado. Input e Output tem palettes separadas (p.ex. ``id_cnj``
   e ``str | list[str]`` no Input, ``str`` no Output).

2. **Nomes deprecados são proibidos** em schemas novos. A constante
   ``DEPRECATED_SYNONYMS`` mapeia as substituições; declarar um desses
   nomes em schema novo reintroduz a divergência e quebra o teste.

:data:`TYPE_GRACE_PERIOD` documenta as excecoes de tipo conhecidas,
cada uma com o motivo: TJPI/TJGO nao convertem ``data_publicacao`` para
``date`` (pendente de limpeza no parser) e as linhas da Corte IDH no TJPR
saem sem ``processo`` (permanente, imposta pela fonte).
"""
from __future__ import annotations

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
from tests.schemas._registro import INPUT_SCHEMAS, OUTPUT_SCHEMAS, SchemaMapeado, resolve, schemas_mapeados

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
    "relatora": "relator",
    "nr_processo": "numero_processo (Input) / processo (Output)",
    "numero_unico": "processo (Output)",
    "numero_cnj": "numero_processo (Input) / id_cnj em consulta CNJ",
    "classe_cnj": "classe",
    "classe_judicial": "classe",
    "assunto_cnj": "assunto",
    "assunto_principal": "assunto",
    # refs #232 — singular canonico para IDs de filtro de busca (cjpg/cjsg).
    "classes": "classe",
    "assuntos": "assunto",
    "varas": "vara",
    # Onde procurar ``pesquisa``. ``inteiro_teor`` fica de fora: e coluna de
    # texto integral no Output de TRF3 e TJPI.
    "campo": "buscar_em",
    "query_scope": "buscar_em",
}


# Excecoes de tipo keyed por (nome_da_classe, nome_do_campo). Documentam
# divergencias conhecidas e o motivo. Remover a entrada quando a correcao
# entrar. Entradas permanentes, impostas pela fonte, dizem isso no comentario.
TYPE_GRACE_PERIOD: dict[tuple[str, str], str] = {
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
    # Com ``incluir_corte_idh=True``, as linhas da Corte IDH saem sem
    # processo: o portal nao tem numero para esses casos. Excecao permanente.
    (
        "OutputCJSGTJPR",
        "processo",
    ): "TJPR: linhas da Corte IDH (incluir_corte_idh=True) nao tem processo",
}


def _is_output(class_name: str) -> bool:
    return class_name.startswith("Output")


def _all_schema_cases():
    """Toda classe Input + Output mapeada, sem repetir as compartilhadas (id da primeira entrada)."""
    primeira: dict[type[BaseModel], SchemaMapeado] = {}
    for mapping in (INPUT_SCHEMAS, OUTPUT_SCHEMAS):
        for par in schemas_mapeados(mapping):
            primeira.setdefault(par.schema, par)
    return [pytest.param(par, id=f"{par.id}.{par.classe}") for par in primeira.values()]


SCHEMA_CASES = _all_schema_cases()


@pytest.mark.parametrize("par", SCHEMA_CASES)
def test_canonical_field_types_are_consistent(par: SchemaMapeado):
    """Campos com nome canonico carregam o tipo declarado na base/mixin.

    Input e Output tem palettes separadas: um campo ``id_cnj`` num Input
    segue ``CnjInputBase`` (``str | list[str]``); num Output segue
    ``OutputCnjConsultaBase`` (``str``).
    """
    schema_cls, class_name = par.schema, par.classe
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


@pytest.mark.parametrize("par", SCHEMA_CASES)
def test_no_deprecated_synonyms_in_schemas(par: SchemaMapeado):
    """Rejeita nomes de DEPRECATED_SYNONYMS em qualquer schema mapeado.

    Ver CONTRIBUTING.md > Schemas pydantic > Nomes e tipos canônicos.
    """
    schema_cls, class_name = par.schema, par.classe
    proibidos = [
        f"{name} (use {DEPRECATED_SYNONYMS[name]})"
        for name in schema_cls.model_fields
        if name in DEPRECATED_SYNONYMS
    ]
    if proibidos:
        items = "\n * ".join(proibidos)
        pytest.fail(
            f"{class_name} declara sinonimo deprecado:\n * {items}\n"
            "CONTRIBUTING.md > Schemas pydantic > Nomes e tipos canônicos "
            "documenta a convenção."
        )


def test_grace_period_exceptions_are_still_needed():
    """Cada excecao de TYPE_GRACE_PERIOD aparece no schema que referencia.

    Impede que a lista cresca silenciosamente: quando a correcao entra, a
    entrada precisa sair daqui junto — se nao sair, o teste falha lembrando
    de limpar. Schema que saiu dos mapas tambem deixa a excecao orfa.
    """
    mapeados = {
        class_name: module_path
        for mapping in (INPUT_SCHEMAS, OUTPUT_SCHEMAS)
        for module_path, class_name in mapping.values()
    }
    orphans = [
        f"{class_name}.{field_name}"
        for class_name, field_name in TYPE_GRACE_PERIOD
        if class_name not in mapeados
        or field_name not in resolve(mapeados[class_name], class_name).model_fields
    ]
    if orphans:
        items = "\n * ".join(orphans)
        pytest.fail(
            "TYPE_GRACE_PERIOD tem excecoes que ja nao aparecem no schema "
            f"(remover da lista — a correcao provavelmente ja entrou):\n * {items}"
        )
