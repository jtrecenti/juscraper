"""Paridade entre campos declarados no Output schema e chaves do parser.

Para cada endpoint mapeado em :data:`tests.schemas._registro.OUTPUT_SCHEMAS`
(tribunais e agregadores), o teste carrega o **source dos modulos de parser**
do raspador e verifica que todo campo proprio do Output aparece como string
literal no parser — ``"campo"`` ou ``'campo'``. Busca por substring (nao AST)
e deliberada: pega chaves em dicts literais, listas de whitelist (ex.
``_MAIN_FIELDS``), dicts de rename (ex. ``_FIELD_RENAMES``) e docstrings
que mencionam colunas — tudo que indica que o parser "fala" daquele
campo.

Campo proprio e o que o Output declara sem herdar de uma base contratual
(:data:`BASES_CONTRATUAIS`: :class:`OutputCJSGBase`,
:class:`OutputCnjConsultaBase` e os mixins de Output). So entram na conta as
bases que estao no MRO do Output: um Output que declara ``relator`` por conta
propria, sem o mixin, tem ``relator`` conferido.

Endpoints sem campo proprio ficam fora da parametrizacao; endpoints cujo
parser nao nomeia as colunas no source ficam em :data:`SKIP_REASONS`, e um
teste de orfaos cobra a remocao da entrada quando ela deixa de ser necessaria.

A direcao oposta (coluna entregue que o Output nao declara) e conferida sobre
os samples reais em :mod:`tests.schemas.test_output_columns`.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import typing

import pandas as pd
import pytest
from pydantic import BaseModel

from juscraper.courts._esaj.schemas import OutputCJPGEsaj, OutputCJSGEsajBase
from juscraper.schemas.cjsg import OutputCJSGBase
from juscraper.schemas.consulta import OutputCnjConsultaBase
from juscraper.schemas.mixins import OutputDataPublicacaoMixin, OutputRelatoriaMixin
from tests.schemas._registro import INPUT_SCHEMAS, OUTPUT_SCHEMAS, SchemaMapeado, schemas_mapeados

#: Bases cujos campos sao contrato universal: o parser concreto nao precisa
#: nomea-los (a garantia e estrutural). Os mixins foram promovidos por
#: evidencia (>=10 e >=9 parsers) e auditados caso a caso na subida.
BASES_CONTRATUAIS: tuple[type[BaseModel], ...] = (
    OutputCJSGBase,
    OutputCnjConsultaBase,
    OutputRelatoriaMixin,
    OutputDataPublicacaoMixin,
)

PARES = schemas_mapeados(OUTPUT_SCHEMAS)
PARES_POR_CHAVE = {(par.sigla, par.endpoint): par for par in PARES}

# Parser dinamico (label-based) ou passthrough: nao da para detectar campos
# por substring no source.
_MOTIVO_ESAJ = "o parser do eSAJ monta as chaves a partir dos rotulos do HTML, sem dict literal"
SKIP_REASONS: dict[tuple[str, str], str] = {
    **{
        (par.sigla, par.endpoint): _MOTIVO_ESAJ
        for par in PARES
        if issubclass(par.schema, (OutputCJSGEsajBase, OutputCJPGEsaj))
    },
    # STF: parser renomeia 6 chaves e repassa o resto do _source da API.
    ("stf", "listar_decisoes"): "STF parser e passthrough do _source — extra=allow e o contrato",
    # DataJud: Output e pivot + extra=allow.
    ("datajud", "listar_processos"): "DataJud passthrough ES _source — extra=allow e o contrato",
}


def _parser_sources(par: SchemaMapeado) -> str:
    """Concatena o source dos modulos de parser que existem para ``par``.

    Candidatos, no pacote do raspador (``juscraper.courts.<sigla>`` ou
    ``juscraper.aggregators.<sigla>``) e em cada pacote de familia
    (``_esaj``, ``_trf``, ``_pdpj_sso``...) do MRO do raspador:

    - ``<pacote>.parse`` (convencao #84)
    - ``<pacote>.<endpoint>_parse`` (ex.: ``cjsg_parse`` do TJSP, ``cjpg_parse`` do eSAJ)
    - ``<pacote>.client``, so no pacote do raspador (parser como metodo)

    Modulo inexistente fica de fora pelo ``find_spec``; erro ao importar ou ao
    ler o source de um modulo existente falha o teste.
    """
    pacote = par.raspador.__module__.rpartition(".")[0]
    candidatos = [f"{pacote}.parse", f"{pacote}.{par.endpoint}_parse", f"{pacote}.client"]
    for cls in par.raspador.__mro__:
        familia = cls.__module__.rpartition(".")[0]
        if familia.rpartition(".")[2].startswith("_"):
            candidatos += [f"{familia}.parse", f"{familia}.{par.endpoint}_parse"]
    return "\n".join(
        inspect.getsource(importlib.import_module(modulo))
        for modulo in dict.fromkeys(candidatos)
        if importlib.util.find_spec(modulo) is not None
    )


def _own_fields(output_cls: type[BaseModel]) -> set[str]:
    """Campos do Output menos os das bases contratuais que estao no seu MRO."""
    herdados = {
        nome
        for base in output_cls.__mro__
        if base in BASES_CONTRATUAIS
        for nome in base.model_fields
    }
    return set(output_cls.model_fields) - herdados


def _faltando(par: SchemaMapeado) -> list[str]:
    source = _parser_sources(par)
    assert source, f"nenhum modulo de parser encontrado para {par.id}"
    return sorted(
        campo for campo in _own_fields(par.schema)
        if f'"{campo}"' not in source and f"'{campo}'" not in source
    )


# Outputs sem campos proprios nao tem o que conferir no parser.
CASOS = [pytest.param(par, id=par.id) for par in PARES if _own_fields(par.schema)]


@pytest.mark.parametrize("par", CASOS)
def test_output_fields_appear_in_parser_source(par: SchemaMapeado):
    """Cada campo proprio do Output aparece como string literal no source do parser."""
    reason = SKIP_REASONS.get((par.sigla, par.endpoint))
    if reason:
        pytest.skip(reason)

    missing = _faltando(par)
    assert not missing, (
        f"{par.classe} declara campos que nao aparecem em nenhum parser de {par.sigla}: "
        f"{missing}. Possivel drift: Output foi inchado alem do que o "
        "parser entrega, ou o parser foi alterado e o Output nao acompanhou."
    )


def test_skips_ainda_sao_necessarios():
    """Entrada de SKIP_REASONS e endpoint mapeado cuja conferencia ainda falharia; senao e orfa."""
    sem_mapa = sorted(SKIP_REASONS.keys() - PARES_POR_CHAVE.keys())
    assert not sem_mapa, f"SKIP_REASONS para endpoint sem Output mapeado: {sem_mapa}"
    # Sem campo proprio, ``_faltando`` tambem devolve ``[]``.
    desnecessarios = sorted(chave for chave in SKIP_REASONS if not _faltando(PARES_POR_CHAVE[chave]))
    assert not desnecessarios, (
        f"Remova de SKIP_REASONS (a conferencia ja passa ou nao ha campo proprio): {desnecessarios}"
    )


def _tem_dataframe(tipo: object) -> bool:
    """``pd.DataFrame`` na anotacao, tambem em uniao (``DataFrame | int``) ou ``dict[str, DataFrame]``."""
    return tipo is pd.DataFrame or any(map(_tem_dataframe, typing.get_args(tipo)))


def test_output_mapeado_para_endpoint_que_devolve_dataframe():
    """Endpoint com Input tem Output mapeado se, e so se, devolve DataFrame.

    Os demais (autenticacao, que devolve ``bool``; ``cjsg_ementa`` do TJTO,
    que devolve ``dict``) nao tem colunas a descrever.
    """
    devolvem_dataframe = {
        (par.sigla, par.endpoint)
        for par in schemas_mapeados(INPUT_SCHEMAS)
        if _tem_dataframe(typing.get_type_hints(getattr(par.raspador, par.endpoint))["return"])
    }
    sem_output = sorted(devolvem_dataframe - OUTPUT_SCHEMAS.keys())
    assert not sem_output, f"Endpoints que devolvem DataFrame sem Output mapeado: {sem_output}"
    sobrando = sorted(OUTPUT_SCHEMAS.keys() - devolvem_dataframe)
    assert not sobrando, f"Output mapeado para endpoint sem Input ou que nao devolve DataFrame: {sobrando}"
