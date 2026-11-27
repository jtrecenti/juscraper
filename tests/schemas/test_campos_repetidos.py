"""Meta-teste: schemas da mesma familia nao repetem campos nem validators.

Quando dois schemas de um mesmo tribunal ou familia declaram os mesmos
campos (nome, tipo e default), cada filtro novo precisa ser editado em
todos eles, e uma correcao feita num validator copiado nao chega ao outro.
Foi o que aconteceu com ``numero_recurso`` no ``cjsg`` eSAJ (#782) e com os
pares ``listar``/``contar`` do DataJud e do PDPJ.

A familia de um schema e o pacote dele (``courts.tjes``) ou, quando o
raspador do pacote herda de uma familia compartilhada (``courts._esaj``,
``courts._trf``, ``aggregators._pdpj_sso``), essa familia: assim
``tjsp/schemas.py`` e comparado com ``_esaj/schemas.py``.

O teste falha quando dois schemas da mesma familia e do mesmo papel
(entrada com entrada, saida com saida), sem relacao de heranca entre si,
declaram ``LIMITE_CAMPOS`` ou mais campos iguais, ou definem um validator
com o mesmo nome e o mesmo codigo. A correcao e subir o que se repete para
uma base comum no modulo da familia (ver CONTRIBUTING.md > **Schemas
pydantic** > **Campos comuns entre endpoints da mesma familia**). Excecao
deliberada vai em ``EXCECOES`` com o motivo.
"""
from __future__ import annotations

import importlib
import inspect
import itertools
import pkgutil
import re
import textwrap

import pytest
from pydantic import BaseModel, model_validator

import juscraper
from juscraper import _SCRAPERS

# Tres campos iguais ja sao um bloco de filtros copiado; dois aparecem por
# coincidencia em schemas pequenos (ex.: ``classe`` + ``assunto``).
LIMITE_CAMPOS = 3

# (schema_a, schema_b) -> motivo. Nomes no formato ``pacote.Classe``, em
# ordem alfabetica dentro do par.
EXCECOES: dict[tuple[str, str], str] = {
    ("courts._esaj.OutputCJPGEsaj", "courts._esaj.OutputCJSGEsaj"): (
        "Saidas de parsers diferentes (cjpg e cjsg) que coincidem em nomes "
        "canonicos de coluna; nao ha bloco comum a extrair."
    ),
    ("courts._esaj.OutputCJPGEsaj", "courts.tjsp.OutputCJSGTJSP"): (
        "Saidas de parsers diferentes (cjpg e cjsg) que coincidem em nomes "
        "canonicos de coluna; nao ha bloco comum a extrair."
    ),
    # Pares do cjsg eSAJ: base comum em andamento no PR da sessao de
    # pendencias do #785. ``test_excecoes_ainda_repetem`` exige tira-los
    # quando o PR mesclar.
    ("courts._esaj.InputCJSGEsajPuro", "courts.tjsp.InputCJSGTJSP"): (
        "Base comum do cjsg eSAJ em andamento (pendencias do #785)."
    ),
    ("courts._esaj.OutputCJSGEsaj", "courts.tjsp.OutputCJSGTJSP"): (
        "Base comum do cjsg eSAJ em andamento (pendencias do #785)."
    ),
}


def _pacote(modulo: str) -> str:
    """``juscraper.courts.tjsp.schemas`` -> ``courts.tjsp``."""
    partes = modulo.split(".")
    return ".".join(partes[1:3])


def _familias_compartilhadas() -> dict[str, str]:
    """Pacote do raspador -> familia compartilhada (``courts._esaj`` etc.)."""
    familias: dict[str, str] = {}
    for alvo in _SCRAPERS.values():
        modulo, nome = alvo.split(":")
        classe = getattr(importlib.import_module(modulo), nome)
        for base in classe.__mro__:
            pacote_base = _pacote(base.__module__)
            if pacote_base.split(".")[-1].startswith("_"):
                familias[_pacote(modulo)] = pacote_base
                break
    return familias


def _schemas() -> list[type[BaseModel]]:
    encontrados: list[type[BaseModel]] = []
    for info in pkgutil.walk_packages(juscraper.__path__, "juscraper."):
        if not info.name.endswith("schemas"):
            continue
        modulo = importlib.import_module(info.name)
        for _, obj in inspect.getmembers(modulo, inspect.isclass):
            if issubclass(obj, BaseModel) and obj.__module__ == modulo.__name__:
                encontrados.append(obj)
    return encontrados


def _sem_endereco(texto: str) -> str:
    # ``repr`` de validators em ``Annotated`` traz o endereco de memoria.
    return re.sub(r" at 0x[0-9a-f]+", "", texto)


def _campos_proprios(schema: type[BaseModel]) -> dict[str, tuple[str, str]]:
    proprios = schema.__dict__.get("__annotations__", {})
    return {
        nome: (_sem_endereco(repr(info.annotation)), _sem_endereco(repr(info.default)))
        for nome, info in schema.model_fields.items()
        if nome in proprios
    }


def _validators_proprios(schema: type[BaseModel]) -> dict[str, str]:
    decorators = schema.__pydantic_decorators__
    codigos: dict[str, str] = {}
    for grupo in (decorators.field_validators, decorators.model_validators):
        for nome, dec in grupo.items():
            if nome not in vars(schema):  # herdado de outra classe
                continue
            fonte = textwrap.dedent(inspect.getsource(dec.func))
            # O nome da classe aparece na anotacao de retorno; nao conta.
            codigos[nome] = fonte.replace(schema.__name__, "<Schema>")
    return codigos


def _nome(schema: type[BaseModel]) -> str:
    return f"{_pacote(schema.__module__)}.{schema.__name__}"


def _papel(schema: type[BaseModel]) -> str:
    # Filtro de entrada e coluna de saida com o mesmo nome (``classe``) nao
    # sao repeticao: um descreve o que se pede, o outro o que volta.
    return "saida" if "Output" in schema.__name__ else "entrada"


def _pares_da_mesma_familia() -> list[tuple[type[BaseModel], type[BaseModel]]]:
    familias = _familias_compartilhadas()
    por_familia: dict[str, list[type[BaseModel]]] = {}
    for schema in _schemas():
        pacote = _pacote(schema.__module__)
        por_familia.setdefault(familias.get(pacote, pacote), []).append(schema)
    pares = []
    for schemas in por_familia.values():
        for a, b in itertools.combinations(sorted(schemas, key=_nome), 2):
            if _papel(a) != _papel(b) or issubclass(a, b) or issubclass(b, a):
                continue
            pares.append((a, b))
    return pares


def _repeticoes(a: type[BaseModel], b: type[BaseModel]) -> list[str]:
    problemas = []
    campos_a, campos_b = _campos_proprios(a), _campos_proprios(b)
    campos = sorted(n for n in campos_a if campos_b.get(n) == campos_a[n])
    if len(campos) >= LIMITE_CAMPOS:
        problemas.append(f"campos repetidos: {campos}")
    val_a, val_b = _validators_proprios(a), _validators_proprios(b)
    validators = sorted(n for n in val_a if val_b.get(n) == val_a[n])
    if validators:
        problemas.append(f"validators copiados: {validators}")
    return problemas


PARES = _pares_da_mesma_familia()


@pytest.mark.parametrize(
    ("a", "b"), PARES, ids=[f"{_nome(a)}-{_nome(b)}" for a, b in PARES],
)
def test_schemas_da_mesma_familia_nao_repetem_declaracoes(
    a: type[BaseModel], b: type[BaseModel],
) -> None:
    if (_nome(a), _nome(b)) in EXCECOES:
        pytest.skip(EXCECOES[(_nome(a), _nome(b))])
    problemas = _repeticoes(a, b)
    assert not problemas, (
        f"{_nome(a)} e {_nome(b)} repetem declaracoes ({'; '.join(problemas)}). "
        "Suba o que se repete para uma base comum no modulo da familia."
    )


def test_excecoes_ainda_repetem() -> None:
    """Excecao que deixou de repetir sai de ``EXCECOES``."""
    por_nome = {(_nome(a), _nome(b)): (a, b) for a, b in PARES}
    obsoletas = [par for par in EXCECOES if par not in por_nome or not _repeticoes(*por_nome[par])]
    assert not obsoletas, f"Remova de EXCECOES: {obsoletas}"


def test_detector_acha_repeticao() -> None:
    """Garante que o detector nao passa vazio (ex.: se a coleta quebrar)."""

    class _A(BaseModel):
        x: int = 0
        y: str | None = None
        z: bool = False

    class _B(BaseModel):
        x: int = 0
        y: str | None = None
        z: bool = False

    assert _repeticoes(_A, _B) == ["campos repetidos: ['x', 'y', 'z']"]

    class _C(BaseModel):
        x: int = 0

        @model_validator(mode="after")
        def _checa(self) -> _C:
            return self

    class _D(BaseModel):
        x: int = 0

        @model_validator(mode="after")
        def _checa(self) -> _D:
            return self

    assert _repeticoes(_C, _D) == ["validators copiados: ['_checa']"]
    assert len(PARES) > 50
