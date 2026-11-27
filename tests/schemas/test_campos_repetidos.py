"""Meta-teste: schemas da mesma familia nao repetem filtros nem validators.

Quando dois schemas de entrada da mesma familia declaram os mesmos filtros,
cada filtro novo precisa ser editado em todos eles, e uma correcao feita num
validator copiado nao chega ao outro. Foi o que aconteceu com
``numero_recurso`` no ``cjsg`` eSAJ (#782) e com os pares ``listar``/``contar``
do DataJud e do PDPJ.

Regra (resumida em CONTRIBUTING.md > **Schemas pydantic**):

- A familia de um schema e o pacote dele (``courts.tjes``) e, se o modulo de
  schemas importa de uma familia compartilhada (``courts._esaj``,
  ``aggregators._pdpj_sso``), tambem essa familia: assim ``tjsp/schemas.py``
  e comparado com ``_esaj/schemas.py``.
- Compara-se entrada com entrada e saida com saida, sem relacao de heranca
  entre os dois schemas.
- Falha: dois schemas de entrada com ``LIMITE_CAMPOS`` ou mais campos
  declarados iguais (``FieldInfo`` igual: tipo, default e restricoes), ou
  dois schemas com o mesmo validator escrito no corpo de cada um.
- Saidas so entram na checagem de validators: colunas de parsers diferentes
  repetem nomes canonicos (``classe``, ``comarca``) por convencao.
- Correcao: subir o que se repete para uma base comum. Excecao deliberada
  vai em ``EXCECOES`` com o motivo.
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

# Tres filtros iguais ja sao um bloco copiado; dois aparecem por
# coincidencia em schemas pequenos (ex.: ``classe`` + ``assunto``).
LIMITE_CAMPOS = 3

# (schema_a, schema_b) -> motivo. Nomes no formato ``pacote.Classe``, em
# ordem alfabetica dentro do par. ``test_excecoes_ainda_repetem`` exige tirar
# a excecao quando o par deixa de repetir.
EXCECOES: dict[tuple[str, str], str] = {}

_FAMILIA_COMPARTILHADA = re.compile(r"juscraper\.(courts|aggregators)\._")


def _pacote(modulo: str) -> str:
    """``juscraper.courts.tjsp.schemas`` -> ``courts.tjsp``."""
    return ".".join(modulo.split(".")[1:3])


def _nome(schema: type[BaseModel]) -> str:
    return f"{_pacote(schema.__module__)}.{schema.__name__}"


def _papel(schema: type) -> str | None:
    # Filtro de entrada e coluna de saida com o mesmo nome (``classe``) nao
    # sao repeticao: um descreve o que se pede, o outro o que volta.
    nome = schema.__name__.lstrip("_")
    if nome.startswith("Input"):
        return "entrada"
    if nome.startswith("Output"):
        return "saida"
    return None


def _grupos() -> dict[tuple[str, str], list[type[BaseModel]]]:
    """(familia, papel) -> schemas definidos nos modulos de schemas."""
    grupos: dict[tuple[str, str], list[type[BaseModel]]] = {}
    for info in pkgutil.walk_packages(juscraper.__path__, "juscraper."):
        if not info.name.endswith("schemas"):
            continue
        modulo = importlib.import_module(info.name)
        familias = {_pacote(modulo.__name__)} | {
            _pacote(obj.__module__)
            for obj in vars(modulo).values()
            if _FAMILIA_COMPARTILHADA.match(getattr(obj, "__module__", None) or "")
        }
        for _, schema in inspect.getmembers(modulo, inspect.isclass):
            papel = _papel(schema)
            if papel is None or not issubclass(schema, BaseModel) or schema.__module__ != modulo.__name__:
                continue
            for familia in familias:
                grupos.setdefault((familia, papel), []).append(schema)
    return grupos


def _pares() -> list[tuple[type[BaseModel], type[BaseModel]]]:
    pares = {
        (a, b)
        for schemas in _grupos().values()
        for a, b in itertools.combinations(sorted(schemas, key=_nome), 2)
        if not (issubclass(a, b) or issubclass(b, a))
    }
    return sorted(pares, key=lambda par: (_nome(par[0]), _nome(par[1])))


def _campos_proprios(schema: type[BaseModel]) -> dict[str, str]:
    # ``repr`` do FieldInfo cobre tipo, default e restricoes de ``Field(...)``;
    # o endereco de memoria de validators em ``Annotated`` nao conta.
    proprios = vars(schema).get("__annotations__", {})
    return {
        nome: re.sub(r" at 0x[0-9a-f]+", "", repr(info))
        for nome, info in schema.model_fields.items()
        if nome in proprios
    }


def _validators_proprios(schema: type[BaseModel]) -> dict[str, str]:
    """Nome -> codigo dos validators escritos no corpo do proprio schema."""
    decorators = schema.__pydantic_decorators__
    codigos: dict[str, str] = {}
    for grupo in (decorators.field_validators, decorators.model_validators):
        for nome, dec in grupo.items():
            # Herdado de outra classe ou funcao de modulo reaproveitada.
            if not dec.func.__qualname__.startswith(f"{schema.__qualname__}."):
                continue
            fonte = textwrap.dedent(inspect.getsource(dec.func))
            # O nome da classe aparece na anotacao de retorno; nao conta.
            codigos[nome] = fonte.replace(schema.__name__, "<Schema>")
    return codigos


def _repeticoes(a: type[BaseModel], b: type[BaseModel]) -> list[str]:
    problemas = []
    if _papel(a) == "entrada":
        campos_a, campos_b = _campos_proprios(a), _campos_proprios(b)
        campos = sorted(n for n in campos_a if campos_b.get(n) == campos_a[n])
        if len(campos) >= LIMITE_CAMPOS:
            problemas.append(f"campos repetidos: {campos}")
    val_a, val_b = _validators_proprios(a), _validators_proprios(b)
    validators = sorted(n for n in val_a if val_b.get(n) == val_a[n])
    if validators:
        problemas.append(f"validators copiados: {validators}")
    return problemas


PARES = _pares()


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
        "Suba o que se repete para uma base comum (ver docstring deste modulo)."
    )


def test_excecoes_ainda_repetem() -> None:
    """Excecao que deixou de repetir sai de ``EXCECOES``."""
    por_nome = {(_nome(a), _nome(b)): (a, b) for a, b in PARES}
    obsoletas = [par for par in EXCECOES if par not in por_nome or not _repeticoes(*por_nome[par])]
    assert not obsoletas, f"Remova de EXCECOES: {obsoletas}"


def test_detector_acha_repeticao() -> None:
    """Garante que o detector nao passa vazio (ex.: se a coleta quebrar)."""

    class InputA(BaseModel):
        x: int = 0
        y: str | None = None
        z: bool = False

    class InputB(BaseModel):
        x: int = 0
        y: str | None = None
        z: bool = False

    assert _repeticoes(InputA, InputB) == ["campos repetidos: ['x', 'y', 'z']"]

    class OutputC(BaseModel):
        x: int = 0

        @model_validator(mode="after")
        def _checa(self) -> OutputC:
            return self

    class OutputD(BaseModel):
        x: int = 0

        @model_validator(mode="after")
        def _checa(self) -> OutputD:
            return self

    assert _repeticoes(OutputC, OutputD) == ["validators copiados: ['_checa']"]
    assert len(PARES) > 50
